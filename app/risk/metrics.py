"""Métricas auxiliares de riesgo: retornos, volatilidad y escalado por horizonte.

CONVENCIÓN: todas las funciones de riesgo devuelven *pérdidas positivas*.
Una pérdida del 3% se representa como 0.03 (positivo).
"""
from __future__ import annotations

import numpy as np


def log_returns(prices: np.ndarray) -> np.ndarray:
    """Retornos logarítmicos a partir de una serie de precios."""
    prices = np.asarray(prices, dtype=float)
    if len(prices) < 2:
        return np.array([], dtype=float)
    return np.diff(np.log(prices))


def simple_returns(prices: np.ndarray) -> np.ndarray:
    """Retornos simples (cambio porcentual) a partir de una serie de precios."""
    prices = np.asarray(prices, dtype=float)
    if len(prices) < 2:
        return np.array([], dtype=float)
    return prices[1:] / prices[:-1] - 1.0


def annualized_volatility(returns: np.ndarray, trading_days: int = 252) -> float:
    """Volatilidad anualizada (desviación estándar muestral) de una serie de retornos."""
    returns = np.asarray(returns, dtype=float)
    if len(returns) < 2:
        return 0.0
    vol_daily = np.std(returns, ddof=1)
    return float(vol_daily * np.sqrt(trading_days))


def scale_var_by_horizon(var_1d: float, horizon_days: int) -> float:
    """Escala VaR de 1 día a N días bajo la raíz del tiempo (i.i.d.).

    NOTA: es una aproximación estándar de la industria (Basel II/III para
    el horizonte de 10 días: VaR_10d = VaR_1d * sqrt(10)).
    """
    return float(var_1d * np.sqrt(horizon_days))