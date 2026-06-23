from fastapi import FastAPI, Form, Response, APIRouter, Header, HTTPException
from pydantic import BaseModel
import requests
import os
import json
import base64
import redis
import google.auth.transport.requests
from google.oauth2 import service_account

router = APIRouter()

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
# Helper interno — lógica compartida de publicación de evento en Particle.
# Ambos endpoints (Twilio y Dart) la usan; un solo lugar donde corregir.
# ---------------------------------------------------------------------------
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
    token      = os.getenv("FCM_TEST_TOKEN")
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    access_token = _get_fcm_access_token()

    url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    payload = {
        "message": {
            "token": token,
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
                    "channel_id": "tanque_canal"   # ← debe coincidir
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
    print(f"[FCM] status={response.status_code} | {response.text}")
    return response.status_code == 200

async def _guardar_en_redis(ph: float, level: float, step: int):
    """
    Guarda el estado actual del tanque en Redis.
    TTL de 300 segundos (5 min) — si el Boron deja de publicar,
    los datos expiran solos y no quedan valores obsoletos.
    """
    client = await redis.asyncio.from_url(os.getenv("REDIS_URL"))
    await client.hset("tanque:estado", mapping={
        "ph":    str(ph),
        "level": str(level),
        "step":  str(step),
    })
    await client.expire("tanque:estado", 300)
    await client.aclose()
    print(f"[Redis] estado guardado → pH={ph} | nivel={level}% | paso={step}")

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

    print(f"[Boron] device={data.device_id} | "
          f"pH={ph} | nivel={level}% | paso={step}")

    await _guardar_en_redis(ph, level, step)
    _enviar_fcm(ph, level, step)

    return {"ok": True}





