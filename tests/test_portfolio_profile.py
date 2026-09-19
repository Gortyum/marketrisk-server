"""Tests del núcleo puro del perfil de riesgo (candidato A).

Atacan directamente la interface del módulo (matriz de retornos +
exposiciones -> PortfolioProfile), sin base de datos.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from app.risk.metrics import annualized_volatility
from app.risk.portfolio_profile import portfolio_risk_profile


def _returns_matrix(n_days: int = 300, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end=datetime(2024, 12, 31), periods=n_days, freq="B")
    a = rng.normal(0.0005, 0.015, n_days)
    b = rng.normal(0.0002, 0.02, n_days)
    return pd.DataFrame({"AAPL": a, "MSFT": b}, index=dates)


def test_profile_returns_market_value_and_weighting():
    rets = _returns_matrix()
    exposures = {"AAPL": 10_000.0, "MSFT": 30_000.0}
    profile = portfolio_risk_profile("Demo", rets, exposures, {"AAPL": "equity", "MSFT": "equity"})

    assert profile.portfolio_name == "Demo"
    assert profile.market_value == pytest.approx(40_000.0)
    assert set(profile.var_by_method) == {"historical", "parametric", "monte_carlo"}
    for measure in profile.var_by_method.values():
        assert 0 < measure.var < profile.market_value
        assert measure.expected_shortfall >= measure.var


def test_profile_sensitivities_and_stress():
    rets = _returns_matrix()
    exposures = {"AAPL": 10_000.0, "MSFT": 30_000.0}
    profile = portfolio_risk_profile("Demo", rets, exposures, {"AAPL": "equity", "MSFT": "equity"})

    assert len(profile.sensitivities) == 2
    aapl_sens = next(s for s in profile.sensitivities if s.symbol == "AAPL")
    assert aapl_sens.exposure == pytest.approx(10_000.0)
    assert aapl_sens.annualized_volatility == pytest.approx(
        annualized_volatility(rets["AAPL"].to_numpy())
    )

    assert "equity_crash" in profile.stress
    crash = profile.stress["equity_crash"]
    # Shocks default -20% sobre exposiciones totales.
    assert crash.impact == pytest.approx(-0.20 * 40_000.0)
    assert set(crash.details) == {"AAPL", "MSFT"}


def test_profile_custom_scenarios():
    rets = _returns_matrix()
    exposures = {"AAPL": 10_000.0, "MSFT": 30_000.0}
    scenarios = {"aapl_crash": {"AAPL": -0.50}}
    profile = portfolio_risk_profile("Demo", rets, exposures, scenarios=scenarios)

    assert set(profile.stress) == {"aapl_crash"}
    assert profile.stress["aapl_crash"].impact == pytest.approx(-5_000.0)


def test_profile_raises_on_zero_value():
    rets = _returns_matrix()
    with pytest.raises(ValueError):
        portfolio_risk_profile("Demo", rets, {"AAPL": 0.0, "MSFT": 0.0})


def test_profile_is_affected_by_diversification():
    """A igual exposición total, 2 activos poco correlacionados < 1 activo solo."""
    rng = np.random.default_rng(3)
    dates = pd.date_range(end="2024-12-31", periods=400, freq="B")
    shocks = rng.normal(0.0, 0.02, 400)
    # MSFT está correlacionado a 0.5 con AAPL y con la mitad de volatilidad.
    m = rng.normal(0.0, 0.01, 400)
    aapl = shocks
    msft = 0.5 * shocks + m * np.sqrt(1 - 0.25)
    rets = pd.DataFrame({"AAPL": aapl, "MSFT": msft}, index=dates)

    solo = portfolio_risk_profile("Solo", rets[["AAPL"]], {"AAPL": 100_000.0})
    duo = portfolio_risk_profile("Duo", rets, {"AAPL": 50_000.0, "MSFT": 50_000.0})
    # El VaR del dúo (diversificado) debe quedar por debajo del de solo-AAPL.
    assert duo.var_by_method["parametric"].var < solo.var_by_method["parametric"].var