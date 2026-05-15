from fastapi import FastAPI, Form, Response
import requests
import os

app = FastAPI()

# Configuración mediante variables de entorno en Railway
# Recuerda configurar PARTICLE_CLIENT_ID, PARTICLE_CLIENT_SECRET y BORON1_ID
CLIENT_ID = os.getenv("PARTICLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("PARTICLE_CLIENT_SECRET")
DEVICE_ID = os.getenv("BORON1_ID")

@app.post("/webhook-twilio")
async def handle_whatsapp(Body: str = Form(...)):
    """
    Recibe el mensaje de Twilio y dispara un evento en Particle
    si se detecta la palabra clave 'consulta'.
    """
    mensaje = Body.lower()
    
    # Registro de actividad en los logs de Railway
    print(f"Procesando mensaje: {mensaje}")
    
    if "consulta" in mensaje:
        url = f"https://api.particle.io/v1/devices/{DEVICE_ID}/events"
        
        payload = {
            "name": "recibir-whatsapp",
            "data": "consultar_ph",
            "private": "true"
        }
        
        # Autenticación de API User mediante Basic Auth (ID, Secret)
        response = requests.post(url, auth=(CLIENT_ID, CLIENT_SECRET), data=payload)
        
        if response.status_code in [200, 201]:
            return Response(content="OK - Evento enviado", media_type="text/plain")
        else:
            print(f"Error en Particle: {response.text}")
            return Response(content="Error en Particle Cloud", status_code=500)
            
    return Response(content="Mensaje ignorado", media_type="text/plain")