from flask import Flask, request
import requests
import os

app = Flask(__name__)

# Configuración (Usa variables de entorno en Railway)
PARTICLE_TOKEN = os.getenv("PARTICLE_TOKEN")
DEVICE_ID = os.getenv("DEVICE_ID")

@app.route("/webhook-twilio", methods=['POST'])
def handle_whatsapp():
    # 1. Recibir datos de Twilio
    incoming_msg = request.form.get('Body', '').lower()
    
    # 2. Filtrar mensaje
    if "consulta" in incoming_msg:
        # 3. Disparar evento en Particle
        url = f"https://api.particle.io/v1/devices/{DEVICE_ID}/events"
        data = {
            "name": "recibir-whatsapp",
            "data": "consultar_ph",
            "private": "true"
        }
        headers = {"Authorization": f"Bearer {PARTICLE_TOKEN}"}
        
        response = requests.post(url, data=data, headers=headers)
        
        if response.status_code == 200:
            return "OK", 200
            
    return "Ignorado", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))