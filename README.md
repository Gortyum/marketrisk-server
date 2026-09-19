# https://marketrisk-ui.vercel.app/
# Market Risk Analysis & Reporting API

Backend de análisis de riesgo de mercado en Python: pipeline ETL, modelos de
riesgo (VaR histórico/paramétrico/Monte Carlo, Expected Shortfall), stress
testing y reportes ejecutivos, expuestos como API REST con FastAPI.

## Stack

- **FastAPI** + Uvicorn: API REST con documentación interactiva en `/docs`.
- **SQLAlchemy 2** + SQLite: persistencia de instrumentos, precios, posiciones y resultados.
- **Pandas / NumPy**: procesamiento vectorizado (ETL y cómputo de riesgo).
- **Pydantic v2**: validación de entradas/salidas.
- **pytest**: suite de tests unitarios y de integración.

## Estructura

```
curso/
├── backend/                       # este backend (hermano de frontend/)
│   ├── app/
│   │   ├── main.py                # Aplicación FastAPI
│   │   ├── config.py              # Configuración (env-overridable)
│   │   ├── database.py            # Engine, sesión y Base declarativa
│   │   ├── api/routes/            # Endpoints REST
│   │   │   ├── etl.py             #   /etl/upload, /etl/instruments
│   │   │   ├── portfolio.py       #   /portfolios/* and positions
│   │   │   └── risk.py            #   /risk/{instrument|portfolio}/...
│   │   ├── models/                # ORM: instruments, price_history, portfolios, positions
│   │   ├── schemas/               # Pydantic
│   │   ├── etl/
│   │   │   ├── extractors.py      # CSV / JSON
│   │   │   ├── transformers.py    # limpieza, validación, forward-fill
│   │   │   ├── loaders.py         # upsert en SQLite
│   │   │   └── pipeline.py        # orquestación extract -> transform -> load
│   │   ├── risk/
│   │   │   ├── var.py             # VaR histórico, paramétrico, Monte Carlo + ES
│   │   │   ├── metrics.py         # retornos, volatilidad, escalado por horizonte
│   │   │   ├── normal.py          # cuantiles normal estándar sin scipy
│   │   │   └── stress.py          # stress testing por escenarios
│   │   └── services/              # lógica de orquestación (risk_service, reporting)
│   ├── scripts/generate_sample_data.py  # genera data/sample/sample_prices.csv
│   ├── data/sample/sample_prices.csv    # datos sintéticos (6 instrumentos, 2 años)
│   └── tests/                     # pytest
└── frontend/                      # dashboard web (consume la API)
└── start.ps1                      # arranque de producción (build + FastAPI)
```

## Instalación

Dependencias de producción (fijadas en `requirements.txt`):

```powershell
cd F:\progra\curso\backend
python -m venv ..\.venv
..\.venv\Scripts\python -m pip install -r requirements.txt
```

Para desarrollo/tests (añade pytest y httpx):

```powershell
..\.venv\Scripts\python -m pip install -r requirements-dev.txt
```

> El entorno virtual vive en `F:\progra\curso\.venv`, a nivel de `curso/`
> (compartido entre `backend/` y `frontend/`). Un venv de Windows graba rutas
> absolutas, así que no se debe mover una vez creado.

## Arranque

En `F:\progra\curso\backend`:

```powershell
..\.venv\Scripts\python -m uvicorn app.main:app --reload
```

- Swagger UI: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

La base de datos `market_risk.db` se crea automáticamente al arrancar.

## Producción

La API y el dashboard (build de React en `frontend/dist/`) se sirven desde el
**mismo origen**, así que no hace falta CORS ni proxy. Un solo comando desde
`F:\progra\curso`:

```powershell
.\start.ps1          # npm run build (si falta dist/) + uvicorn 0.0.0.0:8099
.\start.ps1 -NoBuild # solo levanta el servidor, sin reconstruir
```

- Dashboard: http://localhost:8099/
- API: http://localhost:8099/health — docs: http://localhost:8099/docs

Puntos a tener en cuenta en despliegue:

- **Un solo worker**: la API usa SQLite; más de un worker de uvicorn provoca
  bloqueos de escritura. `start.ps1` corre un único proceso (lo correcto aquí).
- **Interfaz de red**: `--host 0.0.0.0` expone el servicio en la red local.
  Detrás de un proxy/reverse-proxy usa `--proxy-headers` (ya incluido).
- **Base de datos**: por defecto `backend/market_risk.db` (auto-creada).
  Sobrescríbela con `COURSE_DATABASE_URL` en un `.env` de `backend/`
  (ver `.env.example`) si quieres persistencia en otra ruta.
- **CORS**: desactivado por defecto (mismo origen). Si el dashboard se sirve
  desde otro dominio, fija `COURSE_ALLOW_ORIGINS=https://dominio` (lista
  separada por comas).
- **Backup/limpieza**: `market_risk.db` y `.dist/` no se versionan; regenerar la
  base es trivial (ETL idempotente). El build se reproduce con `npm run build`.

## Flujo de uso (end-to-end)

1. **Cargar datos** (ETL) con el CSV de muestra:

   ```powershell
   curl -X POST "http://127.0.0.1:8000/etl/upload" -F "file=@data/sample/sample_prices.csv" -F "asset_class=equity"
   ```

2. **Crear un portafolio y posiciones**:

   ```powershell
   curl -X POST http://127.0.0.1:8000/portfolios -H "Content-Type: application/json" -d '{"name":"Demo"}'
   curl -X POST http://127.0.0.1:8000/portfolios/1/positions -H "Content-Type: application/json" -d '{"instrument_id":1,"quantity":1000}'
   ```

3. **Calcular VaR del portafolio** (los métodos: `historical`, `parametric`, `monte_carlo`):

   ```powershell
   curl -X POST http://127.0.0.1:8000/risk/portfolios/1/var -H "Content-Type: application/json" -d '{"method":"monte_carlo","confidence_level":0.99}'
   ```

4. **Stress test** (escenarios por defecto o personalizados):

   ```powershell
   curl -X POST http://127.0.0.1:8000/risk/portfolios/1/stress -H "Content-Type: application/json" -d '{"scenarios":{"equity_crash":{"AAPL":-0.20}}}'
   ```

5. **Reporte ejecutivo consolidado** (VaR x método + stress + sensibilidades):

   ```powershell
   curl -X POST http://127.0.0.1:8000/risk/portfolios/1/report -H "Content-Type: application/json" -d '{}'
   ```

## Tests

En `F:\progra\curso\backend`:

```powershell
..\.venv\Scripts\python -m pytest tests -v
```

## Convenciones numéricas

- Los VaR y Expected Shortfall se devuelven como **pérdida en USD** (positivos).
- El VaR de un solo instrumento escala el VaR % por su último precio.
- El VaR de portafolio usa la matriz de covarianzas real (no una aproximación
  por componentes) y Monte Carlo simula con correlación vía descomposición de
  Cholesky.
- El ETL es idempotente: reprocesar el mismo archivo no duplica precios.

## Configuración por entorno

| Variable               | Default                              |
| ---------------------- | ------------------------------------ |
| `COURSE_DATABASE_URL`  | `sqlite:///<proyecto>/market_risk.db` |
| `COURSE_ALLOW_ORIGINS` | vacío (sin CORS, mismo origen)       |
| `COURSE_*`             | demás parámetros en `app/config.py`  |

## Despliegue cloud (Railway + Vercel)

Backend → **Railway**, frontend → **Vercel** (orígenes distintos, por eso el
CORS configurable). El `Procfile` de `backend/` fija el comando de arranque
(`$PORT` lo inyecta Railway).

Variables a definir en el panel de **Railway**:

| Variable               | Ejemplo                                        |
| ---------------------- | ---------------------------------------------- |
| `COURSE_ALLOW_ORIGINS` | `https://market-risk.vercel.app` (o varios, separados por coma) |
| `COURSE_DATABASE_URL`  | `postgresql+psycopg://user:pass@host:port/db` (si usas Railway Postgres) |

> Sin Postgres queda SQLite (archivo local): funciona, pero en Railway el
> filesystem es efímero y los datos se pierden al redeployar. Para persistir,
> añade un plugin Postgres y apunta `COURSE_DATABASE_URL` a su conexión
> (el código ya es dialect-portable y trae el driver `psycopg`).
> Origen del deploy de Railway = `backend/`.

Variable a definir en el panel de **Vercel** (se inyecta en el build):

| Variable        | Ejemplo                                   |
| --------------- | ----------------------------------------- |
| `VITE_API_BASE` | `https://course-backend.up.railway.app`   |

> Vercel: framework Vite (build `npm run build`, output `dist/`). Sin
> `VITE_API_BASE`, el bundle llama a la API desde su propio dominio y falla.
