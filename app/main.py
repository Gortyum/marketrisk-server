"""FastAPI application: Market Risk Analysis & Reporting API."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import etl, portfolio, risk
from app.config import settings
from app.database import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "Backend de análisis de riesgo de mercado: pipeline ETL, VaR "
        "(histórico/paramétrico/Monte Carlo), stress testing y reportes."
    ),
    lifespan=lifespan,
)

# CORS solo si se configura COURSE_ALLOW_ORIGINS (API y dashboard comparten
# origen en producción; en dev se usa el proxy de Vite).
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(etl.router)
app.include_router(portfolio.router)
app.include_router(risk.router)


@app.get("/health", tags=["Salud"])
def health() -> dict[str, str]:
    """Comprobación de que el servicio está levantado."""
    return {"status": "ok", "app": settings.app_name, "version": settings.version}


# Sirve el dashboard (React build en frontend/dist/; fallback al dir frontend/),
# desde la raíz, sin tapar la API.
_frontend = Path(__file__).resolve().parent.parent.parent / "frontend"
_dist = _frontend / "dist"
_static = _dist if _dist.is_dir() else _frontend
if _static.is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="dashboard")