"""Tests unitarios de los modelos de VaR."""
from __future__ import annotations

import numpy as np
import pytest

from app.risk import (
    annualized_volatility,
    compute_var,
    expected_shortfall,
    historical_var,
    monte_carlo_var,
    parametric_var,
)
from app.risk.metrics import log_returns
from app.risk.normal import norm_ppf


def test_historical_var_known_percentile():
    # Pérdidas uniformes en [-1, 1]: su p95 (VaR) vale 0.90.
    rng = np.random.default_rng(7)
    returns = rng.uniform(-1.0, 1.0, 5000)
    var, es = historical_var(returns, confidence_level=0.95)
    assert var == pytest.approx(0.90, abs=0.02)
    assert es > var


def test_parametric_var_matches_z_score():
    rng = np.random.default_rng(1)
    returns = rng.normal(0.0, 0.02, 5000)
    var, _ = parametric_var(returns, confidence_level=0.99)
    # VaR paramétrico = z_0.99 * sigma
    assert var == pytest.approx(norm_ppf(0.99) * returns.std(ddof=1), rel=0.05)


def test_monte_carlo_var_runs_and_positive():
    rng = np.random.default_rng(3)
    returns = rng.normal(0.0001, 0.02, 1000)
    var, es = monte_carlo_var(returns, confidence_level=0.95, n_simulations=20_000)
    assert var > 0
    assert es >= var


def test_var_zero_for_singleton_series():
    assert historical_var(np.array([1.0])) == (0.0, 0.0)
    assert parametric_var(np.array([1.0])) == (0.0, 0.0)


def test_expected_shortfall_dominates_var():
    losses = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    var = np.quantile(losses, 0.5)
    es = expected_shortfall(losses, 0.5)
    assert np.quantile(losses, 0.5) <= es


def test_annualized_volatility_scales_with_sqrt_252():
    rng = np.random.default_rng(5)
    returns = rng.normal(0, 0.01, 1000)
    daily_vol = returns.std(ddof=1)
    assert annualized_volatility(returns) == pytest.approx(daily_vol * np.sqrt(252))


def test_parametric_var_scales_with_horizon():
    rng = np.random.default_rng(9)
    returns = rng.normal(0, 0.02, 2000)
    var_1d, _ = parametric_var(returns, 0.95, scale=1)
    var_10d, _ = parametric_var(returns, 0.95, scale=10)
    assert var_10d == pytest.approx(var_1d * np.sqrt(10), rel=0.05)


# --------------------------------------------------------- compute_var (B)
def test_compute_var_dispatch_unknown_method_raises():
    with pytest.raises(ValueError):
        compute_var(np.array([0.1, -0.1, 0.2]), method="bogus")


def test_compute_var_historical_scales_with_sqrt_horizon():
    rng = np.random.default_rng(11)
    returns = rng.normal(0, 0.02, 5000)
    var_1d, _ = compute_var(returns, "historical", 0.95, horizon_days=1)
    var_10d, _ = compute_var(returns, "historical", 0.95, horizon_days=10)
    assert var_10d == pytest.approx(var_1d * np.sqrt(10), rel=0.02)


def test_compute_var_takes_returns_not_prices():
    """compute_var exige retornos: precios en leve deriva no dan VaR enorme."""
    prices = np.linspace(100.0, 200.0, 260)  # tendencia lineal perfecta
    returns = log_returns(prices)
    var_pct, _ = compute_var(returns, "historical", 0.95, 1)
    # Retornos ~ constantes -> pérdida por dólar mínima, no del orden del precio.
    assert var_pct < 0.01
    # Antes este bug existía: con precios pasados como retornos, el VaR era ~ $100.
    assert compute_var(np.array([100.0]), "historical", 0.95, 1) == (0.0, 0.0)