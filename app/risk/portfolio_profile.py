"""Núcleo puro del perfil de riesgo de un portafolio.

Recibe los datos ya materializados (matriz de retornos, exposiciones por
posición) y devuelve TODO el riesgo del portafolio en un solo objeto tipado:
VaR + ES por cada método, sensibilidades y stress por escenario.

No toca la base de datos ni la red: el adaptador que la lee es
`RiskService` (app/services/risk_service.py). La interface es la superficie
de test de toda la matemática de riesgo de portafolio.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .metrics import annualized_volatility
from .stress import SAMPLE_SCENARIOS, StressRunner
from .var import METHODS, compute_var


@dataclass(frozen=True)
class PositionSensitivity:
    symbol: str
    asset_class: str
    exposure: float          # valor de mercado de la posición (USD)
    annualized_volatility: float


@dataclass(frozen=True)
class FactorContribution:
    symbol: str
    asset_class: str
    exposure: float
    annualized_volatility: float
    delta: float             # sensibilidad de primer orden (≈ valor de mercado)
    gamma: float             # segunda derivada (opciones; 0 sin opciones)
    vega: float              # sensibilidad a vol (opciones; 0 sin opciones)
    contribution: float      # parte del VaR total atribuible a este factor (USD)
    share: float             # fracción de 0..1; la suma de todas = 1


@dataclass(frozen=True)
class ClassContribution:
    asset_class: str
    exposure: float
    contribution: float
    share: float


@dataclass(frozen=True)
class FactorDecomposition:
    portfolio_name: str
    market_value: float
    total_var: float
    confidence_level: float
    horizon_days: int
    method: str
    classes: list[ClassContribution]
    factors: list[FactorContribution]


@dataclass(frozen=True)
class VaRMeasure:
    var: float               # pérdida (USD, positiva)
    expected_shortfall: float


@dataclass(frozen=True)
class ScenarioResult:
    impact: float            # impacto en P&L (USD, negativo = pérdida)
    details: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioProfile:
    portfolio_name: str
    market_value: float
    var_by_method: dict[str, VaRMeasure]
    sensitivities: list[PositionSensitivity]
    stress: dict[str, ScenarioResult]


def _portfolio_returns(returns_matrix: pd.DataFrame, weights: np.ndarray) -> np.ndarray:
    """Serie de retornos diarios del portafolio (pérdida % por día)."""
    return returns_matrix.to_numpy() @ weights


def _monte_carlo_portfolio(
    returns_matrix: pd.DataFrame,
    weights: np.ndarray,
    confidence_level: float,
    horizon_days: int,
    n_simulations: int,
    seed: int,
) -> tuple[float, float]:
    """Monte Carlo de portafolio con correlación real (descomposición de Cholesky)."""
    cov = returns_matrix.cov().to_numpy()
    mu = returns_matrix.mean().to_numpy()
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n_simulations, returns_matrix.shape[1]))
    try:
        a = np.linalg.cholesky(cov)
    except np.linalg.LinAlgError:
        cov = cov + np.eye(cov.shape[0]) * 1e-12
        a = np.linalg.cholesky(cov)
    sim_returns = mu * horizon_days + (a @ z.T).T * np.sqrt(horizon_days)
    losses = -(sim_returns @ weights)
    var = float(np.quantile(losses, confidence_level))
    es = float(losses[losses >= var].mean())
    return var, es


def portfolio_risk_profile(
    portfolio_name: str,
    returns_matrix: pd.DataFrame,
    exposures: dict[str, float],
    asset_classes: dict[str, str] | None = None,
    *,
    confidence_level: float = 0.95,
    horizon_days: int = 1,
    n_simulations: int = 10_000,
    seed: int = 42,
    scenarios: dict[str, dict[str, float]] | None = None,
) -> PortfolioProfile:
    """Perfil de riesgo completo de un portafolio, en un solo pase.

    - `returns_matrix`: pandas DataFrame indexado por fecha, columnas = símbolo.
    - `exposures`: symbol -> valor de mercado de la posición (quantity × último precio).
    - `asset_classes`: symbol -> clase de activo (para sensibilidad).
    """
    total_value = sum(exposures.values())
    if total_value <= 0:
        raise ValueError("El valor del portafolio es cero.")
    weights = np.array([exposures[s] / total_value for s in returns_matrix.columns])

    port_returns = _portfolio_returns(returns_matrix, weights)
    var_by_method: dict[str, VaRMeasure] = {}
    for method in METHODS:
        if method == "monte_carlo":
            var, es = _monte_carlo_portfolio(
                returns_matrix, weights, confidence_level, horizon_days, n_simulations, seed
            )
        else:
            var, es = compute_var(
                port_returns, method, confidence_level, horizon_days, n_simulations, seed
            )
        var_by_method[method] = VaRMeasure(var=var * total_value, expected_shortfall=es * total_value)

    classes = asset_classes or {}
    sensitivities = [
        PositionSensitivity(
            symbol=symbol,
            asset_class=classes.get(symbol, "unknown"),
            exposure=exposures[symbol],
            annualized_volatility=annualized_volatility(
                returns_matrix[symbol].to_numpy(dtype=float)
            ),
        )
        for symbol in returns_matrix.columns
    ]

    runner = StressRunner(current_prices=exposures, weights={s: 1.0 for s in exposures})
    stress = {
        name: ScenarioResult(impact=report["impact"], details=report["details"])
        for name, report in runner.run_scenarios(scenarios or SAMPLE_SCENARIOS).items()
    }

    return PortfolioProfile(
        portfolio_name=portfolio_name,
        market_value=total_value,
        var_by_method=var_by_method,
        sensitivities=sensitivities,
        stress=stress,
    )


def factor_decomposition(
    portfolio_name: str,
    returns_matrix: pd.DataFrame,
    exposures: dict[str, float],
    asset_classes: dict[str, str] | None = None,
    *,
    confidence_level: float = 0.95,
    horizon_days: int = 1,
    method: str = "historical",
) -> FactorDecomposition:
    """Descompone la contribución al VaR por factor de riesgo (Euler).

    Substituye la varianza del portafolio por la covarianza real de los
    retornos alineados y usa la derivada de Euler: la participación de cada
    factor es `w_i * (Σ w)_i / (w' Σ w)`. Estas participaciones suman 1 y se
    aplican al VaR total (USD) del portafolio.

    Los instrumentos del feed son lineales: delta = valor de mercado y
    gamma/vega = 0 (la entrada no modela opciones). Se exponen igual para
    que el contrato sea estable si mañana llega un feed con opciones.
    """
    total_value = sum(exposures.values())
    if total_value <= 0:
        raise ValueError("El valor del portafolio es cero.")
    columns = list(returns_matrix.columns)
    weights = np.array([exposures[s] / total_value for s in columns])
    cov = returns_matrix.cov().to_numpy()
    portfolio_var = float(weights @ cov @ weights)
    if portfolio_var <= 0:
        raise ValueError("La varianza del portafolio no es positiva.")

    shares = (weights * (cov @ weights)) / portfolio_var
    port_returns = _portfolio_returns(returns_matrix, weights)
    var_pct, _ = compute_var(port_returns, method, confidence_level, horizon_days)
    total_var = var_pct * total_value

    classes_map = asset_classes or {}
    factors = [
        FactorContribution(
            symbol=symbol,
            asset_class=classes_map.get(symbol, "unknown"),
            exposure=exposures[symbol],
            annualized_volatility=annualized_volatility(
                returns_matrix[symbol].to_numpy(dtype=float)
            ),
            delta=exposures[symbol],
            gamma=0.0,
            vega=0.0,
            contribution=float(shares[i]) * total_var,
            share=float(shares[i]),
        )
        for i, symbol in enumerate(columns)
    ]

    aggregated: dict[str, dict[str, float]] = {}
    for f in factors:
        bucket = aggregated.setdefault(f.asset_class, {"exposure": 0.0, "contribution": 0.0, "share": 0.0})
        bucket["exposure"] += f.exposure
        bucket["contribution"] += f.contribution
        bucket["share"] += f.share
    classes = [
        ClassContribution(
            asset_class=asset_class,
            exposure=values["exposure"],
            contribution=values["contribution"],
            share=values["share"],
        )
        for asset_class, values in sorted(aggregated.items())
    ]

    return FactorDecomposition(
        portfolio_name=portfolio_name,
        market_value=total_value,
        total_var=total_var,
        confidence_level=confidence_level,
        horizon_days=horizon_days,
        method=method,
        classes=classes,
        factors=factors,
    )