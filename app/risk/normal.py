"""Funciones de la distribución normal estándar sin dependencia de scipy.

norm_ppf usa la aproximación racional de Acklam (precisión ~1e-9), que es
suficiente para cálculo de VaR. El pdf se obtiene directamente con numpy.
"""
from __future__ import annotations

import numpy as np


def norm_ppf(p: float | np.ndarray) -> float | np.ndarray:
    """Inversa de la CDF normal estándar (cuantil), sin scipy.

    Implementa la aproximación racional de Peter Acklam
    (http://home.online.no/~pjacklam/notes/invnorm/), válida para 0 < p < 1.
    """
    p = np.asarray(p, dtype=float)
    # Coeficientes de Acklam (dos ramas según la cola).
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    plow = 0.02425
    phigh = 1 - plow

    x = np.empty_like(p)
    lo = p < plow
    hi = p > phigh
    mid = ~(lo | hi)

    if np.any(lo):
        q = np.sqrt(-2 * np.log(p[lo]))
        x[lo] = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
                ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if np.any(hi):
        q = np.sqrt(-2 * np.log(1 - p[hi]))
        x[hi] = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
                ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if np.any(mid):
        q = p[mid] - 0.5
        r = q * q
        x[mid] = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
                 (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)

    return x.item() if x.ndim == 0 else x


def norm_pdf(x: float | np.ndarray) -> float | np.ndarray:
    """Función de densidad de la normal estándar."""
    x = np.asarray(x, dtype=float)
    out = np.exp(-0.5 * x * x) / np.sqrt(2 * np.pi)
    return out.item() if out.ndim == 0 else out