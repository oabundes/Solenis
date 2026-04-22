# Solenis - Reporte de Lectura de PH

Esta es una aplicación web responsiva y moderna construida con:
- **Backend:** FastAPI (Python) que se conecta a Supabase.
- **Frontend:** HTML5, CSS3 Vanilla y JavaScript (Vanilla).
- **Gráficas:** Chart.js para renderizar la telemetría interactiva vertical (PH sobre X y tiempo sobre Y).

## Requisitos previos

- Python 3.8 o superior instalado.
- Opcional: Credenciales de la base de datos de Supabase.

## Instalación

1. Instala las dependencias de Python descritas en `requirements.txt`:
```cmd
pip install -r requirements.txt
```

2. Configura tu Base de Datos Supabase (OPCIONAL):
Si deseas usar la base de datos real, edita el archivo `.env` en este directorio y coloca tu URL y Key de Supabase:
```
SUPABASE_URL=tu_supabase_url
SUPABASE_KEY=tu_anon_key
```

> **Nota:** Si no configuras las variables `.env`, la aplicación funcionará usando *Datos Simulados (Mocking)* de manera transparente, lo que es perfecto para probar la interfaz visual y la gráfica.

## Uso

Para arrancar el servidor web de la aplicación, y servir la interfaz:

```cmd
python main.py
```

Luego, abre tu navegador web e ingresa a: **http://localhost:8000**
