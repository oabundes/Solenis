from fastapi import FastAPI, Form, Response, APIRouter
import requests
import os

router = APIRouter()

# Configuración mediante variables de entorno en Railway
# Recuerda configurar PARTICLE_CLIENT_ID, PARTICLE_CLIENT_SECRET y BORON1_ID
CLIENT_ID = os.getenv("PARTICLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("PARTICLE_CLIENT_SECRET")
DEVICE_ID = os.getenv("BORON2_ID")
ACCESS_TOKEN = os.getenv("PARTICLE_ACCESS_TOKEN")

@router.post("/webhook-twilio")
async def handle_whatsapp(Body: str = Form(...)):
    """
    Recibe el mensaje de Twilio y dispara un evento en Particle
    si se detecta la palabra clave 'consulta'.
    """
    mensaje = Body.lower()
    
    # Registro de actividad en los logs de Railway
    print(f"Procesando mensaje: {mensaje}")
    
    if "consulta" in mensaje:
        url = f"https://api.particle.io/v1/devices/events"
        
        payload = {
            "name": "recibir-whatsapp",
            "data": "consultar_ph",
            "private": "true"
        }
        print("URL:", url)
        print("Payload:", payload)  
        print("Token existe:", bool(ACCESS_TOKEN))
        # Autenticación de API User mediante Basic Auth (ID, Secret)
        response = requests.post(url, headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}, data=payload)
        
        if response.status_code in [200, 201]:
            return Response(content="OK - Evento enviado", media_type="text/plain")
        else:
            print(f"Error en Particle: {response.text}")
            return Response(content="Error en Particle Cloud", status_code=500)
            
    return Response(content="Mensaje ignorado", media_type="text/plain")