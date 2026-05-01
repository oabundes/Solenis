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
    _TZ_LOCAL = timezone(timedelta(hours=-6))

app = FastAPI()

url: str = os.environ.get("SUPABASE_URL", "")
key: str = os.environ.get("SUPABASE_KEY", "")

# Mapeo número (frontend) → texto (base de datos)
EVENTO_MAP = {
    1: "DESCARGA",
    2: "INICIA",
    3: "TERMINA"
}
# Mapeo inverso texto → número
EVENTO_REVERSE = {v: k for k, v in EVENTO_MAP.items()}

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
    evento: Optional[int] = None

@app.get("/api/data", response_model=List[DataPoint])
def get_data(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    evento: Optional[List[int]] = Query(default=None)
):
    tz_local = _TZ_LOCAL

    # --- Validación: rango máximo de 2 meses ---
    if start_date and end_date:
        try:
            d_start = date.fromisoformat(start_date[:10])
            d_end   = date.fromisoformat(end_date[:10])
            if (d_end - d_start).days > 62:
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

    def convertir_fila(row):
        """Convierte timestamp UTC→México y evento texto→número."""
        if row.get('timestamp'):
            utc_dt = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
            row['timestamp'] = utc_dt.astimezone(tz_local).strftime('%Y-%m-%dT%H:%M:%S')
        ev_raw = row.get('evento')
        if isinstance(ev_raw, str):
            row['evento'] = EVENTO_REVERSE.get(ev_raw.strip().upper(), None)
        return row

    if not supabase:
        import random
        now = datetime.now()
        mock = []
        for i in range(50):
            t = now - timedelta(hours=i * 2)
            ph_value = round(random.uniform(6.5, 8.5) + (1.5 if i % 12 == 0 else 0), 2)
            mock.append({"timestamp": t.isoformat(), "PH": ph_value, "evento": (i % 3) + 1})
        if start_date:
            mock = [d for d in mock if d["timestamp"][:10] >= start_date[:10]]
        if end_date:
            mock = [d for d in mock if d["timestamp"][:10] <= end_date[:10]]
        if evento:
            mock = [d for d in mock if d.get("evento") in evento]
        return [convertir_fila(r) for r in mock]

    # --- Consulta real a Supabase ---
    # Usar offset -06:00 para que Postgres compare correctamente con timestamptz
    gte_val = (start_date[:10] + "T00:00:00-06:00") if start_date else None
    lte_val = (end_date[:10]   + "T23:59:59-06:00") if end_date   else None

    query = (
        supabase.table("pHLogg")
        .select("timestamp, PH, evento")
        .order("timestamp", desc=True)
    )

    if gte_val:
        query = query.gte("timestamp", gte_val)
    if lte_val:
        query = query.lte("timestamp", lte_val)

    # Convertir números → texto para filtrar en la BD
    if evento:
        eventos_texto = [EVENTO_MAP[e] for e in evento if e in EVENTO_MAP]
        if eventos_texto:
            query = query.in_("evento", eventos_texto)

    response = query.execute()
    return [convertir_fila(row) for row in response.data]

# Servir archivos estáticos
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
