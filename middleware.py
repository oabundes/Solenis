from fastapi import FastAPI, Form, Response, APIRouter
import requests
import os

router = APIRouter()

ACCESS_TOKEN = os.getenv("PARTICLE_ACCESS_TOKEN")
DEVICE_ID = os.getenv("BORON2_ID")  # ← confirma si es BORON1 o BORON2

@router.post("/webhook-twilio")
async def handle_whatsapp(Body: str = Form(...)):
    mensaje = Body.lower()
    print(f"Procesando mensaje: {mensaje}")

    if "consulta" in mensaje:
        url = "https://api.particle.io/v1/devices/events"

        payload = {
            "name": "recibir_whatsapp",
            "data": "consulta",
            "private": True  # ✅ booleano
        }

        print("Token existe:", bool(ACCESS_TOKEN))

        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
            data=payload
        )

        if response.status_code in [200, 201]:
            return Response(content="OK - Evento enviado", media_type="text/plain")
        else:
            print(f"Error en Particle: {response.text}")
            return Response(content="Error en Particle Cloud", status_code=500)

    return Response(content="Mensaje ignorado", media_type="text/plain")