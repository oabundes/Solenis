from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
import os
from datetime import datetime
import uvicorn
from dotenv import load_dotenv

load_dotenv()

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

@app.get("/api/data", response_model=List[DataPoint])
def get_data(start_date: Optional[str] = None, end_date: Optional[str] = None):
    if not supabase:
        # Mock data for testing when credentials aren't set
        import random
        from datetime import timedelta
        now = datetime.now()
        mock = []
        for i in range(50):
            t = now - timedelta(hours=i*2)
            # Add some variations to make the chart look nice
            ph_value = round(random.uniform(6.5, 8.5) + (1.5 if i%12==0 else 0), 2)
            mock.append({
                "timestamp": t.isoformat(),
                "PH": ph_value
            })
        
        # Filter mock data if dates are provided
        if start_date:
            mock = [d for d in mock if d["timestamp"] >= start_date]
        if end_date:
            end_date_str = end_date + "T23:59:59" if len(end_date) == 10 else end_date
            mock = [d for d in mock if d["timestamp"] <= end_date_str]
            
        return mock
        
    query = supabase.table("pHLogg").select("timestamp", "PH").order("timestamp", desc=True)
    
    if start_date:
        query = query.gte("timestamp", start_date)
    if end_date:
        if len(end_date) == 10:
            query = query.lte("timestamp", end_date + "T23:59:59")
        else:
            query = query.lte("timestamp", end_date)
            
    response = query.execute()
    return response.data

# Servir los archivos estáticos en la raíz
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
