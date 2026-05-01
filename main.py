from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
import os
from datetime import datetime, date, timedelta, timezone
import uvicorn
from dotenv import load_dotenv
load_dotenv()

# Zona horaria local con fallback para Windows (sin tzdata instalado)
try:
    from zoneinfo import ZoneInfo
    _TZ_LOCAL = ZoneInfo('America/Mexico_City')
except Exception:
    # Fallback: UTC-6 (hora del centro de México sin horario de verano)
    _TZ_LOCAL = timezone(timedelta(hours=-6))

app = FastAPI()

url: str = os.environ.get("SUPABASE_URL", "")
key: str = os.environ.get("SUPABASE_KEY", "")

# Los valores reales en Supabase son strings (ej: 'DESCARGA', 'INICIA', 'TERMINA')

try:
    from supabase import create_client, Client
    supabase: Client = create_client(url, key) if url and key else None
except ImportError:
    print("Supabase library not installed. Running with mock data.")
    supabase = None
except Exception as e:
    print(f"Error connecting to Supabase: {e}")
    supabase = None

class DataPoint(BaseModel):
    timestamp: str
    PH: float
    evento: Optional[str] = None

@app.get("/api/data", response_model=List[DataPoint])
def get_data(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    evento: Optional[List[str]] = Query(default=None)
):
    tz_local = _TZ_LOCAL

    # --- Validación: rango máximo de 2 meses ---
    if start_date and end_date:
        try:
            d_start = date.fromisoformat(start_date[:10])
            d_end   = date.fromisoformat(end_date[:10])
            if (d_end - d_start).days > 62:  # ~2 meses
                raise HTTPException(
                    status_code=400,
                    detail="El intervalo de fechas no puede ser mayor a 2 meses."
                )
            if d_end < d_start:
                raise HTTPException(
                    status_code=400,
                    detail="La fecha final no puede ser anterior a la fecha inicial."
                )
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de fecha inválido.")

    def convertir_timestamp(data):
        for row in data:
            if row.get('timestamp'):
                utc_dt = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
                row['timestamp'] = utc_dt.astimezone(tz_local).strftime('%Y-%m-%dT%H:%M:%S')
        return data

    if not supabase:
        # Mock data para pruebas
        import random
        now = datetime.now()
        mock = []
        eventos_ciclo = ["DESCARGA", "INICIA", "TERMINA"]
        for i in range(50):
            t = now - timedelta(hours=i * 2)
            ph_value = round(random.uniform(6.5, 8.5) + (1.5 if i % 12 == 0 else 0), 2)
            mock.append({
                "timestamp": t.isoformat(),
                "PH": ph_value,
                "evento": eventos_ciclo[i % 3]
            })

        if start_date:
            mock = [d for d in mock if d["timestamp"] >= start_date]
        if end_date:
            end_date_str = end_date + "T23:59:59" if len(end_date) == 10 else end_date
            mock = [d for d in mock if d["timestamp"] <= end_date_str]
        if evento:
            mock = [d for d in mock if d.get("evento") in evento]

        return convertir_timestamp(mock)

    # --- Consulta real a Supabase ---
    query = (
        supabase.table("pHLogg")
        .select("timestamp", "PH", "evento")
        .order("timestamp", desc=True)
    )

    if start_date:
        query = query.gte("timestamp", start_date)
    if end_date:
        lte_val = end_date + "T23:59:59" if len(end_date) == 10 else end_date
        query = query.lte("timestamp", lte_val)
    if evento:
        query = query.in_("evento", evento)

    response = query.execute()
    return convertir_timestamp(response.data)

# Servir los archivos estáticos en la raíz
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
