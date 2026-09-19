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


class VaREngineRequest(BaseModel):
    """Selectores del motor central de riesgo."""

    segment: str = Field(default="all", pattern="^(all|fx|equity|commodity|rate)$")
    confidence_level: float = Field(default=0.95, gt=0.5, lt=1.0)
    horizon_days: int = Field(default=1, ge=1, le=30)
    lookback_days: int = Field(default=252, ge=30)
    method: VaRMethod = VaRMethod.historical
    n_simulations: int = Field(default=10_000, ge=1_000, le=500_000)


class VaREngineResult(BaseModel):
    """Resultado con trazabilidad: de dónde salió cada cifra."""

    target: str
    segment: str
    method: str
    confidence_level: float
    horizon_days: int
    portfolio_value: float
    var_value: float
    expected_shortfall: float
    worst_historical_loss: float
    n_observations: int
    n_factors: int
    n_positions: int
    calculation_time_ms: float


class StressReportOut(BaseModel):
    """Baseline vs. escenario: valor, P&L y VaR antes/después del shock."""

    scenario_name: str
    baseline_value: float
    stressed_value: float
    pnl: float
    var_baseline: float
    var_stressed: float
    n_positions: int


class StressReportRequest(BaseModel):
    """Escenario de estrés: shocks porcentuales por instrumento."""

    scenario_name: str = Field(default="custom", min_length=1, max_length=64)
    shocks: dict[str, float]
    confidence_level: float = Field(default=0.95, gt=0.5, lt=1.0)
    horizon_days: int = Field(default=1, ge=1, le=30)
    lookback_days: int = Field(default=252, ge=30)


class VaRFactorOut(BaseModel):
    symbol: str
    asset_class: str
    exposure: float
    annualized_volatility: float
    delta: float
    gamma: float
    vega: float
    contribution: float
    share: float


class VaRClassOut(BaseModel):
    asset_class: str
    exposure: float
    contribution: float
    share: float


class FactorDecompositionOut(BaseModel):
    """Contribución al VaR por factor y por clase (Euler allocation)."""

    target: str
    portfolio_value: float
    total_var: float
    confidence_level: float
    horizon_days: int
    method: str = "historical"
    classes: list[VaRClassOut]
    factors: list[VaRFactorOut]


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