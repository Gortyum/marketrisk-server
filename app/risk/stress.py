"""Stress testing: aplica shocks a los factores de riesgo y mide el impacto.

Los escenarios son multiplicadores porcentuales sobre los precios base.
Un shock negativo (-20%) significa que el factor cae un 20%.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SAMPLE_SCENARIOS: dict[str, dict[str, float]] = {
    "equity_crash": {"default": -0.20},
    "equity_rally": {"default": 0.15},
    "fx_devaluation": {"default": -0.10},
    "vol_spike": {"default": -0.25},
}


@dataclass
class StressRunner:
    """Aplica una batería de escenarios sobre precios base y calcula impactos."""

    current_prices: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)  # notional / multiplicadores

    def impact(self, shocks: dict[str, float]) -> tuple[float, dict[str, float]]:
        """Calcula el impacto total y por instrumento de un escenario.

        impact_i = price_i * shock_i * weight_i
        """
        details: dict[str, float] = {}
        total = 0.0
        for symbol, price in self.current_prices.items():
            shock = shocks.get(symbol, shocks.get("default", 0.0))
            impact = price * shock * self.weights.get(symbol, 1.0)
            details[symbol] = float(impact)
            total += impact
        return float(total), details

    def run_scenarios(
        self, scenarios: dict[str, dict[str, float]]
    ) -> dict[str, dict]:
        """Ejecuta todos los escenarios y devuelve {nombre: {impact, details}}."""
        results = {}
        for name, shocks in scenarios.items():
            total, details = self.impact(shocks)
            results[name] = {"impact": total, "details": details}
        return results

    def worst_loss(self, report: dict[str, dict]) -> tuple[str, float]:
        """Escenario con la mayor pérdida (menor impacto)."""
        if not report:
            return "", 0.0
        name = min(report, key=lambda k: report[k]["impact"])
        return name, report[name]["impact"]