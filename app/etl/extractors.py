from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {"symbol", "date", "close"}


class Extractor(ABC):
    """Interfaz común para todos los extractores de datos."""

    @abstractmethod
    def extract(self) -> pd.DataFrame:
        """Devuelve datos crudos normalizados con columnas standard."""


class CSVExtractor(Extractor):
    """Extrae series de precios desde un archivo CSV.

    Formato esperado (opcional columnas name/asset_class/currency):

        symbol,date,close
        AAPL,2024-01-02,185.64
    """

    def __init__(self, source: str | Path):
        self.source = Path(source)

    def extract(self) -> pd.DataFrame:
        if not self.source.exists():
            raise FileNotFoundError(f"Archivo de entrada no encontrado: {self.source}")
        df = pd.read_csv(self.source, parse_dates=["date"])
        missing = REQUIRED_COLUMNS - set(df.columns)
        if missing:
            raise ValueError(f"Faltan columnas obligatorias: {sorted(missing)}")
        return df


class JsonExtractor(Extractor):
    """Extrae series de precios desde un archivo JSON:

    [{"symbol": "AAPL", "name": "Apple", "date": "2024-01-02", "close": 185.64}]
    """

    def __init__(self, source: str | Path):
        self.source = Path(source)

    def extract(self) -> pd.DataFrame:
        if not self.source.exists():
            raise FileNotFoundError(f"Archivo de entrada no encontrado: {self.source}")
        df = pd.read_json(self.source)
        df["date"] = pd.to_datetime(df["date"])
        missing = REQUIRED_COLUMNS - set(df.columns)
        if missing:
            raise ValueError(f"Faltan columnas obligatorias: {sorted(missing)}")
        return df