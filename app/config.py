from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    """Configuración centralizada de la aplicación.

    Las variables se pueden sobrescribir desde el entorno o desde un archivo
    ``.env`` en ``backend/`` (p.ej. COURSE_DATABASE_URL) para despliegues en
    otros entornos.
    """

    app_name: str = "Market Risk API"
    version: str = "1.0.0"

    database_url: str = os.getenv(
        "COURSE_DATABASE_URL", f"sqlite:///{BASE_DIR / 'market_risk.db'}"
    )
    default_confidence_level: float = 0.95
    default_horizon_days: int = 1
    default_lookback_days: int = 252

    # Orígenes permitidos para CORS (separados por coma). Vacío = sin CORS
    # (mismo origen: FastAPI sirve también el dashboard).
    cors_origins: list[str] = [
        o.strip() for o in os.getenv("COURSE_ALLOW_ORIGINS", "").split(",") if o.strip()
    ]

    # Umbrales de validación para el pipeline ETL.
    max_missing_ratio: float = 0.3
    negative_price_allowed: bool = False

    data_dir: Path = BASE_DIR / "data"

    def __repr__(self) -> str:
        return f"Settings(database={self.database_url!r})"


settings = Settings()