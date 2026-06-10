from fastapi import FastAPI, Form, Response, APIRouter, Header, HTTPException
from pydantic import BaseModel
import requests
import os

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
            json=payload,          # application/json, no form-encoded
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
