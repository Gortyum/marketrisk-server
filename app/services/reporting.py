"""Generación de reportes de riesgo consolidados para stakeholders."""
from __future__ import annotations

from app.schemas.risk import RiskReport, SensitivityOut
from app.services.risk_service import RiskService


class ReportingService:
    """Arma un reporte de riesgo ejecutivo a partir del perfil de riesgo.

    No vuelve a calcular nada: corta secciones del `RiskProfile` que
    entrega el adapter.
    """

    def __init__(self, session):
        self.service = RiskService(session)

    def build_report(
        self,
        portfolio_id: int,
        *,
        confidence_level: float = 0.95,
        horizon_days: int = 1,
        lookback_days: int = 252,
        n_simulations: int = 10_000,
        scenarios: dict[str, dict[str, float]] | None = None,
    ) -> RiskReport:
        profile = self.service.profile(
            portfolio_id,
            confidence_level=confidence_level,
            horizon_days=horizon_days,
            lookback_days=lookback_days,
            n_simulations=n_simulations,
            scenarios=scenarios,
        )
        return RiskReport(
            portfolio=profile.portfolio_name,
            market_value=profile.market_value,
            var_by_method={m: v.var for m, v in profile.var_by_method.items()},
            stress_by_scenario={k: v.impact for k, v in profile.stress.items()},
            sensitivities=[
                SensitivityOut(
                    instrument=s.symbol,
                    asset_class=s.asset_class,
                    exposure=s.exposure,
                    annualized_volatility=s.annualized_volatility,
                )
                for s in profile.sensitivities
            ],
        )