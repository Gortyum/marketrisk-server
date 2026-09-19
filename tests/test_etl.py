"""Tests del pipeline ETL con datos reales de muestra."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.etl.extractors import CSVExtractor
from app.etl.pipeline import ETLPipeline
from app.etl.transformers import MarketDataTransformer
from app.models.market_data import Instrument
from sqlalchemy import func, select


def test_transformer_rejects_bad_rows_and_dedupes():
    raw = pd.DataFrame(
        {
            "symbol": ["aapl", "AAPL", "msft", " bad ", ""],
            "date": pd.to_datetime(["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
            "close": [100.0, 100.0, 200.0, 300.0, 400.0],
        }
    )
    result = MarketDataTransformer().transform(raw, asset_class="equity")
    assert result.rejected_rows == 1  # símbolo vacío
    assert set(result.instruments["symbol"]) == {"AAPL", "MSFT", "BAD"}
    # Duplicado (mismo símbolo+fecha) eliminado y fechas rellenadas (ffill no aplica aquí).
    assert not result.prices.duplicated(subset=["symbol", "date"]).any()


def test_pipeline_loads_sample_data(db_session, sample_data_dir: Path):
    csv_path = sample_data_dir / "sample_prices.csv"
    assert csv_path.exists(), "Ejecuta primero scripts/generate_sample_data.py"
    result = ETLPipeline(db_session).run(csv_path, asset_class="equity", currency="USD")

    assert result.instruments_loaded >= 1
    assert result.price_rows_loaded > 0
    n_rows = db_session.execute(select(func.count("*")).select_from(Instrument.__table__)).scalar()
    assert n_rows == result.instruments_loaded


def test_pipeline_is_idempotent(db_session, sample_data_dir: Path):
    """Volver a correr el pipeline no duplica precios."""
    csv_path = sample_data_dir / "sample_prices.csv"
    first = ETLPipeline(db_session).run(csv_path)
    second = ETLPipeline(db_session).run(csv_path)
    assert second.price_rows_loaded == 0  # nada nuevo que insertar


def test_missing_csv_raises():
    csv_path = Path("F:/progra/curso/data/inexistente.csv")
    with pytest.raises(FileNotFoundError):
        CSVExtractor(csv_path).extract()