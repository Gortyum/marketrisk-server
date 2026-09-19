from datetime import date

from pydantic import BaseModel, Field


class InstrumentBase(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    asset_class: str
    currency: str = "USD"


class InstrumentCreate(InstrumentBase):
    pass


class InstrumentOut(InstrumentBase):
    id: int

    model_config = {"from_attributes": True}


class PriceRow(BaseModel):
    instrument_id: int
    trade_date: date
    close: float


class PriceHistoryOut(BaseModel):
    trade_date: date
    close: float

    model_config = {"from_attributes": True}


class InstrumentHistoryOut(InstrumentOut):
    prices: list[PriceHistoryOut] = []


class ETLRunRequest(BaseModel):
    """Parámetros opcionales sobre cómo procesar el archivo CSV."""

    asset_class: str = "equity"
    currency: str = "USD"
    name: str | None = None


class ETLRunResponse(BaseModel):
    source: str
    instruments_loaded: int
    price_rows_loaded: int
    rejected_rows: int
    warnings: list[str] = []