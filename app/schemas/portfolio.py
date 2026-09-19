from pydantic import BaseModel, Field


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class PortfolioOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class PositionCreate(BaseModel):
    instrument_id: int
    quantity: float
    weight: float = 1.0


class PositionOut(BaseModel):
    id: int
    portfolio_id: int
    instrument_id: int
    quantity: float
    weight: float

    model_config = {"from_attributes": True}


class PortfolioDetail(PortfolioOut):
    positions: list[PositionOut] = []