from fastapi import FastAPI, Form, Response, APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import requests
import os
import json
import base64
import redis.asyncio as aioredis
import redis
import asyncio
import logging
import google.auth.transport.requests
from google.oauth2 import service_account

# ============ LOGGING ============
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# ============ SSE CONFIGURATION ============
CHANNEL_NAME = "canal_actualizacion_tanque"
HEARTBEAT_INTERVAL = 25  # segundos (Railway/Cloudflare timeout ~30s)
MESSAGE_TIMEOUT = 1.0    # timeout para esperar mensaje en Redis

# ---------------------------------------------------------------------------
# Variables de entorno — validación temprana al importar el módulo.
# Si alguna falta, Railway mostrará el error en los logs de deploy,
# no en tiempo de request.
# ---------------------------------------------------------------------------
ACCESS_TOKEN = os.getenv("PARTICLE_ACCESS_TOKEN")
DEVICE_ID    = os.getenv("BORON2_ID")
APP_API_KEY  = os.getenv("APP_API_KEY")   # opcional: protege /comando-boron

if not ACCESS_TOKEN:
    raise RuntimeError("Variable de entorno PARTICLE_ACCESS_TOKEN no definida")
if not DEVICE_ID:
    raise RuntimeError("Variable de entorno BORON2_ID no definida")

# ---------------------------------------------------------------------------
# SSE Event Generator — Escucha Redis Pub/Sub y envía eventos en tiempo real
# ---------------------------------------------------------------------------
async def event_generator(request: Request):
    """
    Generador que escucha Redis Pub/Sub y envía eventos SSE.
    
    Características:
    - Heartbeat inteligente (25s) para evitar timeouts de proxy
    - Validación de JSON antes de enviar
    - Cierre seguro de recursos
    - Logging para debugging en Railway
    """
    redis_client = None
    pubsub = None
    last_heartbeat = asyncio.get_event_loop().time()
    
    try:
        # Conectarse a Redis con opciones de persistencia
        redis_client = aioredis.from_url(
            os.getenv("REDIS_URL"),
            decode_responses=True,
            socket_keepalive=True,
        )
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(CHANNEL_NAME)
        logger.info(f"[SSE] Cliente conectado, escuchando {CHANNEL_NAME}")
        
        while True:
            # ✅ Verificar desconexión del cliente
            if await request.is_disconnected():
                logger.info("[SSE] Cliente desconectado (cliente cerró conexión)")
                break
            
            # ✅ Escuchar mensaje con timeout
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=MESSAGE_TIMEOUT
                    ),
                    timeout=MESSAGE_TIMEOUT + 0.1
                )
            except asyncio.TimeoutError:
                message = None
            
            current_time = asyncio.get_event_loop().time()
            time_since_heartbeat = current_time - last_heartbeat
            
            # ✅ Si hay mensaje: enviar datos
            if message:
                try:
                    data = message['data']
                    
                    # Validar que sea JSON válido
                    if isinstance(data, str):
                        json.loads(data)  # Verifica que sea JSON válido
                    
                    yield f"data: {data}\n\n"
                    logger.debug(f"[SSE] Evento enviado: {data[:100]}")
                    last_heartbeat = current_time
                    
                except json.JSONDecodeError as e:
                    logger.error(f"[SSE] Dato recibido no es JSON válido: {data} - {e}")
                    continue
                except Exception as e:
                    logger.error(f"[SSE] Error procesando mensaje: {e}")
                    continue
            
            # ✅ Heartbeat inteligente
            elif time_since_heartbeat >= HEARTBEAT_INTERVAL:
                yield ": ping\n\n"
                last_heartbeat = current_time
                logger.debug("[SSE] Heartbeat enviado")
            
            # ✅ Pequeño sleep para no bloquear el loop
            await asyncio.sleep(0.05)
    
    except asyncio.CancelledError:
        logger.info("[SSE] Tarea cancelada (probablemente por Railway/proxy)")
        
    except Exception as e:
        logger.error(f"[SSE] Error no esperado en event_generator: {e}", exc_info=True)
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    finally:
        # ✅ Cierre seguro y completo
        if pubsub:
            try:
                await pubsub.unsubscribe(CHANNEL_NAME)
                await pubsub.close()
                logger.info("[SSE] PubSub cerrado correctamente")
            except Exception as e:
                logger.error(f"[SSE] Error cerrando pubsub: {e}")
        
        if redis_client:
            try:
                await redis_client.close()
                logger.info("[SSE] Cliente Redis cerrado correctamente")
            except Exception as e:
                logger.error(f"[SSE] Error cerrando cliente Redis: {e}")


async def _guardar_y_publicar(ph: float, level: float, step: int):
    """
    Guarda el estado en Redis caché Y publica en Pub/Sub para SSE.
    Una sola conexión, dos operaciones atómicas — más eficiente.
    
    TTL: 300 segundos (5 min) — si el Boron deja de publicar,
    los datos expiran solos y no quedan valores obsoletos.
    """
    try:
        client = aioredis.from_url(os.getenv("REDIS_URL"), decode_responses=True)
        
        # 1. Guardar en hash con TTL
        await client.hset("tanque:estado", mapping={
            "ph":    str(ph),
            "level": str(level),
            "step":  str(step),
        })
        await client.expire("tanque:estado", 300)
        
        # 2. Publicar en Pub/Sub (misma conexión)
        estado_json = json.dumps({"ph": ph, "level": level, "step": step})
        await client.publish(CHANNEL_NAME, estado_json)
        
        await client.aclose()
        logger.info(f"[Redis] Guardado + publicado → pH={ph} | nivel={level}% | paso={step}")
        
    except Exception as e:
        logger.error(f"[Redis] Error: {e}")


PARTICLE_EVENTS_URL = "https://api.particle.io/v1/devices/events"

def _publicar_evento_particle(nombre: str, datos: str) -> tuple[bool, str]:
    """
    Publica un evento en Particle Cloud.
    Devuelve (ok: bool, detalle: str).
    Nunca lanza excepción — los errores se empaquetan en el retorno.
    """
    payload = {
        "name":    nombre,
        "data":    datos,
        "private": True,   # booleano, no string
    }
    try:
        response = requests.post(
            PARTICLE_EVENTS_URL,
            headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
            data=payload,    #<-- from-encoded, no json
            timeout=5,
        )
    except requests.exceptions.Timeout:
        return False, "Timeout: Particle Cloud no respondió en 5 s"
    except requests.exceptions.RequestException as e:
        return False, f"Error de red hacia Particle: {e}"

    if response.status_code in [200, 201]:
        return True, "Evento publicado correctamente"
    else:
        return False, f"Particle respondió HTTP {response.status_code}: {response.text}"


# ---------------------------------------------------------------------------
# Endpoint 1 — Twilio / WhatsApp (conservado sin cambios funcionales)
# Twilio envía POST con body form-encoded; el campo se llama "Body".
# ---------------------------------------------------------------------------
@router.post("/webhook-twilio")
async def handle_whatsapp(Body: str = Form(...)):
    mensaje = Body.lower()
    print(f"[Twilio] Mensaje recibido: {mensaje}")

    if "consulta" in mensaje:
        ok, detalle = _publicar_evento_particle("recibir_whatsapp", "consulta")
        print(f"[Twilio] Particle → ok={ok} | {detalle}")

        if ok:
            return Response(content="OK - Evento enviado", media_type="text/plain")
        else:
            print(f"[Twilio] Error en Particle: {detalle}")
            return Response(content="Error en Particle Cloud", status_code=500)

    return Response(content="Mensaje ignorado", media_type="text/plain")


# ---------------------------------------------------------------------------
# Endpoint 2 — App Dart
# La app envía POST con JSON: {"comando": "consulta"}
# Devuelve JSON: {"ok": bool, "mensaje": str}
#
# Protección opcional con API key: si APP_API_KEY está definida en las
# variables de entorno de Railway, el header x-api-key es obligatorio.
# Si no está definida, el endpoint queda abierto (útil en desarrollo).
# ---------------------------------------------------------------------------
class ComandoRequest(BaseModel):
    comando: str                    # "consulta", "inicio", etc.
    device_id: str | None = None    # reservado para multi-Boron futuro

@router.post("/comando-boron")
async def handle_comando_dart(
    req: ComandoRequest,
    x_api_key: str | None = Header(default=None),
):
    # Validar API key solo si está configurada en el entorno
    if APP_API_KEY and x_api_key != APP_API_KEY:
        raise HTTPException(status_code=401, detail="No autorizado")

    comando = req.comando.strip().lower()
    print(f"[Dart] Comando recibido: '{comando}' | device_id={req.device_id}")

    if comando == "consulta":
        ok, detalle = _publicar_evento_particle("recibir_comando", comando)
        print(f"[Dart] Particle → ok={ok} | {detalle}")

        if ok:
            return {"ok": True,  "mensaje": "Evento enviado al Boron"}
        else:
            return {"ok": False, "mensaje": detalle}

    # Comando no reconocido — no es un error del servidor (200), pero ok=False
    return {"ok": False, "mensaje": f"Comando '{comando}' no reconocido"}


def _get_fcm_access_token() -> str:
    credentials_b64  = os.getenv("FIREBASE_CREDENTIALS")
    credentials_json = base64.b64decode(credentials_b64).decode("utf-8")
    credentials_dict = json.loads(credentials_json)
    credentials = service_account.Credentials.from_service_account_info(
        credentials_dict,
        scopes=["https://www.googleapis.com/auth/firebase.messaging"]
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return credentials.token

def _enviar_fcm(ph: float, level: float, step: int):
    project_id   = os.getenv("FIREBASE_PROJECT_ID")
    access_token = _get_fcm_access_token()

    url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    payload = {
        "message": {
            "topic": "notificaciones_neutralizacion",  # ← Tema global
            "notification": {
                "title": "Tanque de Neutralización",
                "body":  f"pH: {ph} | Nivel: {level}% | Paso: {step}"
            },
            "data": {
                "ph":    str(ph),
                "level": str(level),
                "step":  str(step)
            },
            "android": {
                "priority": "high",
                "notification": {
                    "sound":      "default",
                    "notification_priority": "PRIORITY_HIGH",
                    "visibility": "public",
                    "channel_id": "tanque_canal"
                }
            }
        }
    }
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json"
        },
        json=payload,
        timeout=5
    )
    logger.info(f"[FCM] status={response.status_code} | {response.text}")
    return response.status_code == 200

async def _guardar_en_redis(ph: float, level: float, step: int):
    """
    Guarda el estado actual del tanque en Redis.
    TTL de 300 segundos (5 min) — si el Boron deja de publicar,
    los datos expiran solos y no quedan valores obsoletos.
    """
    try:
        client = aioredis.from_url(os.getenv("REDIS_URL"), decode_responses=True)
        await client.hset("tanque:estado", mapping={
            "ph":    str(ph),
            "level": str(level),
            "step":  str(step),
        })
        await client.expire("tanque:estado", 300)
        await client.aclose()
        logger.info(f"[Redis] estado guardado → pH={ph} | nivel={level}% | paso={step}")
    except Exception as e:
        logger.error(f"[Redis] Error guardando estado: {e}")


@router.get("/estado")
async def get_estado():
    """Devuelve el último estado del tanque guardado en Redis."""
    try:
        client = await aioredis.from_url(os.getenv("REDIS_URL"), decode_responses=True)
        estado = await client.hgetall("tanque:estado")
        await client.aclose()

        if not estado:
            return {"ph": 0.0, "level": 0.0, "step": 0}

        return {
            "ph":    float(estado["ph"]),
            "level": float(estado["level"]),
            "step":  int(estado["step"]),
        }
    except Exception as e:
        logger.error(f"[Redis] Error al leer estado: {e}")
        return {"ph": 0.0, "level": 0.0, "step": 0}


@router.get("/estado-stream")
async def estado_stream(request: Request):
    """
    Endpoint SSE para actualización en tiempo real del estado del tanque.
    
    Uso desde Flutter:
    ```dart
    final response = await client.send(request);
    response.stream.transform(utf8.decoder).listen((event) {
      if (event.startsWith('data: ')) {
        final json = event.substring(6);
        // Procesar estado...
      }
    });
    ```
    """
    return StreamingResponse(
        event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",  # Importante para proxies (Cloudflare, Railway)
            "Connection": "keep-alive",
        }
    )





class BoronData(BaseModel):
    device_id: str | None = None
    ph:        str
    level:     str
    step:      str

@router.post("/from-boron-data")
async def handle_boron_data(data: BoronData):
    ph    = float(data.ph)
    level = float(data.level)
    step  = int(data.step)

    logger.info(f"[Boron] device={data.device_id} | "
                f"pH={ph} | nivel={level}% | paso={step}")

    # Guardar en Redis + publicar en Pub/Sub (una sola operación)
    await _guardar_y_publicar(ph, level, step)
    
    # Enviar notificación FCM
    _enviar_fcm(ph, level, step)

    return {"ok": True}


@router.post("/actualiza-redis")
async def handle_actualiza_redis(data: BoronData):
    ph    = float(data.ph)
    level = float(data.level)
    step  = int(data.step)

    logger.info(f"[Boron] device={data.device_id} | "
                f"pH={ph} | nivel={level}% | paso={step}")

    # Guardar en Redis + publicar en Pub/Sub (una sola operación)
    await _guardar_y_publicar(ph, level, step)
 
    return {"ok": True, "fuente":"redis"}
