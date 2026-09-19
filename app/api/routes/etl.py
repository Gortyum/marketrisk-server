"""Endpoints de ingesta (ETL) de datos de mercado."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.etl.pipeline import ETLPipeline
from app.schemas.market_data import ETLRunRequest, ETLRunResponse, InstrumentOut
from app.models.market_data import Instrument
from sqlalchemy import select

router = APIRouter(prefix="/etl", tags=["ETL"])


@router.post("/upload", response_model=ETLRunResponse)
async def upload_csv(
    file: UploadFile = File(...),
    params: ETLRunRequest = Depends(),
    db: Session = Depends(get_db),
) -> ETLRunResponse:
    """Carga un CSV/JSON de precios mediante el pipeline ETL completo.

    Formato CSV: symbol,date,close (+ opcional name/asset_class/currency)
    """
    if not file.filename:
        raise ValueError("El archivo no tiene nombre.")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".csv", ".json"}:
        raise ValueError("Solo se aceptan archivos CSV o JSON.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        result = ETLPipeline(db).run(
            tmp_path,
            asset_class=params.asset_class,
            currency=params.currency,
            name=params.name,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return ETLRunResponse(
        source=file.filename,
        instruments_loaded=result.instruments_loaded,
        price_rows_loaded=result.price_rows_loaded,
        rejected_rows=result.rejected_rows,
        warnings=result.warnings,
    )


@router.get("/instruments", response_model=list[InstrumentOut])
def list_instruments(db: Session = Depends(get_db)) -> list[Instrument]:
    """Lista los instrumentos disponibles en la base."""
    return list(db.scalars(select(Instrument).order_by(Instrument.symbol)))