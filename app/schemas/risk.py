from enum import Enum

from pydantic import BaseModel, Field


class VaRMethod(str, Enum):
    historical = "historical"
    parametric = "parametric"
    monte_carlo = "monte_carlo"


class VaRRequest(BaseModel):
    confidence_level: float = Field(default=0.95, gt=0.5, lt=1.0)
    horizon_days: int = Field(default=1, ge=1)
    lookback_days: int = Field(default=252, ge=30)
    method: VaRMethod = VaRMethod.historical
    n_simulations: int = Field(default=10_000, ge=1_000, le=500_000)


class VaRResult(BaseModel):
    target: str
    method: str
    confidence_level: float
    horizon_days: int
    var_value: float
    expected_shortfall: float


class SensitivityOut(BaseModel):
    instrument: str
    asset_class: str
    exposure: float
    annualized_volatility: float | None = None


class StressScenario(BaseModel):
    """Una escenario de shock de precios (multiplicadores) por instrumento."""

    name: str
    shocks: dict[str, float]  # instrument -> pct change, p.ej. {"AAPL": -0.20}


class StressResultOut(BaseModel):
    scenario_name: str
    impact: float
    details: dict[str, float] = {}


class RiskReport(BaseModel):
    portfolio: str
    market_value: float
    var_by_method: dict[str, float]
    stress_by_scenario: dict[str, float]
    sensitivities: list[SensitivityOut]