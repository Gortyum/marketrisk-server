"""Implementación de los tres métodos de Value-at-Risk.

Convención de signos: el resultado es una *pérdida* expresada en valores
positivos, y con la misma escala que los retornos de entrada
(retornos en decimal -> VaR en decimal; retornos en $ -> VaR en $).
"""
from __future__ import annotations

import numpy as np

from .normal import norm_pdf, norm_ppf

METHODS = ("historical", "parametric", "monte_carlo")


def _losses(returns: np.ndarray) -> np.ndarray:
    """Convierte retornos en pérdidas positivas."""
    return -np.asarray(returns, dtype=float)


def expected_shortfall(losses: np.ndarray, confidence_level: float) -> float:
    """Expected Shortfall (CVaR): pérdida media más allá del percentil VaR."""
    losses = np.asarray(losses, dtype=float)
    if losses.size == 0:
        return 0.0
    threshold = np.quantile(losses, confidence_level)
    tail = losses[losses >= threshold]
    if tail.size == 0:
        tail = np.array([threshold])
    return float(tail.mean())


def historical_var(returns: np.ndarray, confidence_level: float = 0.95) -> tuple[float, float]:
    """VaR histórico: percentil empírico (1 - confianza) de las pérdidas.

    Usa interpolación lineal (tipo 7 de numpy) para una estimación más
    estable con muestras pequeñas. Devuelve (var, expected_shortfall).
    """
    losses = _losses(returns)
    if losses.size < 2:
        return 0.0, 0.0
    var = float(np.quantile(losses, confidence_level))
    return var, expected_shortfall(losses, confidence_level)


def parametric_var(
    returns: np.ndarray,
    confidence_level: float = 0.95,
    scale: float = 1.0,
) -> tuple[float, float]:
    """VaR paramétrico (delta-normal): asume retornos ~ Normal(mu, sigma).

    var = -mu * scale + z_alpha * sigma * sqrt(scale)
    ES paramétrico = mean + sigma * phi(z) / (1 - alpha)
    """
    returns = np.asarray(returns, dtype=float)
    if returns.size < 2:
        return 0.0, 0.0
    mu = returns.mean() * scale
    sigma = returns.std(ddof=1) * np.sqrt(scale)
    z = norm_ppf(confidence_level)
    var = float(-mu + z * sigma)
    phi_z = norm_pdf(z)
    es = float(mu + sigma * phi_z / (1 - confidence_level))
    return var, es


def monte_carlo_var(
    returns: np.ndarray,
    confidence_level: float = 0.95,
    horizon_days: int = 1,
    n_simulations: int = 10_000,
    seed: int | None = 42,
) -> tuple[float, float]:
    """VaR Monte Carlo: simula trayectorias GBM con drift y sigma históricos.

    Los retornos del último día se escalan por sqrt(horizon_days), que es la
    práctica habitual para horizontes > 1 día con supuesto i.i.d.
    Devuelve (var, expected_shortfall) sobre la distribución simulada.
    """
    returns = np.asarray(returns, dtype=float)
    if returns.size < 2:
        return 0.0, 0.0
    mu = returns.mean()
    sigma = returns.std(ddof=1)
    dt = float(horizon_days)
    rng = np.random.default_rng(seed)
    shocks = rng.standard_normal(n_simulations)
    terminal_returns = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * shocks
    losses = _losses(terminal_returns)
    var = float(np.quantile(losses, confidence_level))
    return var, expected_shortfall(losses, confidence_level)


def compute_var(
    returns: np.ndarray,
    method: str = "historical",
    confidence_level: float = 0.95,
    horizon_days: int = 1,
    n_simulations: int = 10_000,
    seed: int | None = 42,
) -> tuple[float, float]:
    """VaR y ES de una serie de retornos, ya escalados al horizonte.

    Es el ÚNICO dispatch entre métodos y la única política de escalado por
    horizonte:
      - historical: VaR/ES de 1 día escalados con sqrt(horizon) (supuesto i.i.d.);
      - parametric: escala internamente mu y sigma al horizonte (delta-normal);
      - monte_carlo: simula retornos terminales YA al horizonte (sin re-escalar).

    Devuelve pérdidas por dólar (positivas), lista para multiplicar por el
    valor de mercado. Acepta retornos (log o simples), NO precios.
    """
    returns = np.asarray(returns, dtype=float)
    if method == "historical":
        var, es = historical_var(returns, confidence_level)
        scale = float(np.sqrt(horizon_days))
        return var * scale, es * scale
    if method == "parametric":
        return parametric_var(returns, confidence_level, scale=horizon_days)
    if method == "monte_carlo":
        return monte_carlo_var(
            returns,
            confidence_level,
            horizon_days=horizon_days,
            n_simulations=n_simulations,
            seed=seed,
        )
    raise ValueError(f"Método de VaR desconocido: {method!r}")