from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
import os
from datetime import datetime, date, timedelta, timezone
import uvicorn
from dotenv import load_dotenv

from middleware import router as middleware_router

load_dotenv()

try:
    from zoneinfo import ZoneInfo
    _TZ_LOCAL = ZoneInfo('America/Mexico_City')
except Exception:
    _TZ_LOCAL = timezone(timedelta(hours=-6))

app = FastAPI()

url: str = os.environ.get("SUPABASE_URL", "")
key: str = os.environ.get("SUPABASE_KEY", "")

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
    evento: Optional[str] = None   # texto: DESCARGA, INICIA, TERMINA

class InstrumentDataPoint(BaseModel):
    created_at: str
    extracted_value: float
    unit: str
    instrument_type: Optional[str] = None
    image_url: Optional[str] = None

@app.get("/api/instrument_units")
def get_instrument_units():
    if not supabase:
        raise HTTPException(status_code=500, detail="Base de datos Supabase no configurada.")
    try:
        response = supabase.table("instrument_readings").select("unit").execute()
        units = sorted(list(set(row["unit"] for row in response.data if row.get("unit"))))
        return units
    except Exception as e:
        print(f"Error fetching instrument units: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener unidades de Supabase: {e}")

@app.get("/api/instrument_data", response_model=List[InstrumentDataPoint])
def get_instrument_data(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    unit: Optional[str] = None
):
    tz_local = _TZ_LOCAL

    if start_date and end_date:
        try:
            d_start = date.fromisoformat(start_date[:10])
            d_end   = date.fromisoformat(end_date[:10])
            if (d_end - d_start).days > 62:
                raise HTTPException(status_code=400, detail="El intervalo no puede superar 2 meses.")
            if d_end < d_start:
                raise HTTPException(status_code=400, detail="La fecha final no puede ser anterior a la inicial.")
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de fecha inválido.")

    def convertir_timestamp(data):
        for row in data:
            if row.get('created_at'):
                utc_dt = datetime.fromisoformat(row['created_at'].replace('Z', '+00:00'))
                row['created_at'] = utc_dt.astimezone(tz_local).strftime('%Y-%m-%dT%H:%M:%S')
        return data

    if not supabase:
        raise HTTPException(status_code=500, detail="Base de datos Supabase no configurada o desactivada.")

    # Consulta real a Supabase
    gte_val = None
    lte_val = None
    if start_date:
        gte_val = start_date[:10] + "T06:00:00+00:00"
    if end_date:
        d_next = date.fromisoformat(end_date[:10]) + timedelta(days=1)
        lte_val = d_next.isoformat() + "T05:59:59+00:00"

    query = (
        supabase.table("instrument_readings")
        .select("created_at, extracted_value, unit, instrument_type, image_url")
        .order("created_at", desc=True)
    )

    if gte_val:
        query = query.gte("created_at", gte_val)
    if lte_val:
        query = query.lte("created_at", lte_val)
    if unit:
        query = query.eq("unit", unit)

    response = query.execute()
    data = convertir_timestamp(response.data)
    return data

@app.get("/api/parametros")
def get_parametros():
    if not supabase:
        raise HTTPException(status_code=500, detail="Base de datos Supabase no configurada.")
    try:
        response = supabase.table("parametros").select("parametro, valor").in_("parametro", ["MIN_PH_DESC", "MAX_PH_DESC"]).execute()
        result = {row["parametro"]: row["valor"] for row in response.data}
        return result
    except Exception as e:
        print(f"Error fetching parametros: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener parámetros de Supabase: {e}")

@app.get("/api/data", response_model=List[DataPoint])
def get_data(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    evento: Optional[List[str]] = Query(default=None)  # recibe texto directamente
):
    tz_local = _TZ_LOCAL

    if start_date and end_date:
        try:
            d_start = date.fromisoformat(start_date[:10])
            d_end   = date.fromisoformat(end_date[:10])
            if (d_end - d_start).days > 62:
                raise HTTPException(status_code=400, detail="El intervalo no puede superar 2 meses.")
            if d_end < d_start:
                raise HTTPException(status_code=400, detail="La fecha final no puede ser anterior a la inicial.")
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de fecha inválido.")

    def convertir_timestamp(data):
        for row in data:
            if row.get('timestamp'):
                utc_dt = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
                row['timestamp'] = utc_dt.astimezone(tz_local).strftime('%Y-%m-%dT%H:%M:%S')
            # Limpiar espacios del evento
            if isinstance(row.get('evento'), str):
                row['evento'] = row['evento'].strip()
        return data

    if not supabase:
        raise HTTPException(status_code=500, detail="Base de datos Supabase no configurada o desactivada.")

    # Consulta real a Supabase
    # México (UTC-6): 00:00 local = 06:00 UTC, 23:59:59 local = siguiente día 05:59:59 UTC
    gte_val = None
    lte_val = None
    if start_date:
        gte_val = start_date[:10] + "T06:00:00+00:00"
    if end_date:
        d_next = date.fromisoformat(end_date[:10]) + timedelta(days=1)
        lte_val = d_next.isoformat() + "T05:59:59+00:00"

    print(f"DEBUG gte_val: {gte_val}")
    print(f"DEBUG lte_val: {lte_val}")
    print(f"DEBUG evento filtro: {evento}")

    query = (
        supabase.table("pHLogg")
        .select("timestamp, PH, evento")
        .order("timestamp", desc=True)
    )

    if gte_val:
        query = query.gte("timestamp", gte_val)
    if lte_val:
        query = query.lte("timestamp", lte_val)

    response = query.execute()
    data = convertir_timestamp(response.data)

    # Filtrar por evento en Python (después de trim) para evitar problema de espacios en BD
    if evento:
        eventos_limpios = [e.strip().upper() for e in evento]
        data = [row for row in data if (row.get('evento') or '').strip().upper() in eventos_limpios]

    print(f"DEBUG filas devueltas: {len(data)}")
    if data:
        print(f"DEBUG primera fila: {data[0]}")
    return data

app.include_router(middleware_router)

app.mount("/", StaticFiles(directory="static", html=True), name="static")

##app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
