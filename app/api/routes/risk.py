"""Endpoints de análisis y reporte de riesgo de mercado.

Cada endpoint corta una vista del `RiskProfile` que produce el núcleo puro
de riesgo; ninguno vuelve a calcular nada por su cuenta.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.risk import SAMPLE_SCENARIOS
from app.schemas.risk import (
    RiskReport,
    SensitivityOut,
    StressResultOut,
    VaRRequest,
    VaRResult,
)
from app.services.risk_service import InstrumentNotFoundError, RiskService
from app.services.reporting import ReportingService

router = APIRouter(prefix="/risk", tags=["Riesgo"])


@router.post("/instruments/{instrument_id}/var", response_model=VaRResult)
def instrument_var(
    instrument_id: int,
    params: VaRRequest,
    db: Session = Depends(get_db),
) -> VaRResult:
    """Calcula VaR (en USD) para un instrumento individual."""
    try:
        return RiskService(db).var_for_instrument(
            instrument_id,
            confidence_level=params.confidence_level,
            horizon_days=params.horizon_days,
            lookback_days=params.lookback_days,
            method=params.method.value,
            n_simulations=params.n_simulations,
        )
    except InstrumentNotFoundError:
        raise HTTPException(status_code=404, detail="Instrumento sin datos de precios.")


@router.post("/portfolios/{portfolio_id}/var", response_model=VaRResult)
def portfolio_var(
    portfolio_id: int,
    params: VaRRequest,
    db: Session = Depends(get_db),
) -> VaRResult:
    """VaR del portafolio (USD) con el método indicado (slice del perfil)."""
    try:
        profile = RiskService(db).profile(
            portfolio_id,
            confidence_level=params.confidence_level,
            horizon_days=params.horizon_days,
            lookback_days=params.lookback_days,
            n_simulations=params.n_simulations,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    measure = profile.var_by_method[params.method.value]
    return VaRResult(
        target=profile.portfolio_name,
        method=params.method.value,
        confidence_level=params.confidence_level,
        horizon_days=params.horizon_days,
        var_value=measure.var,
        expected_shortfall=measure.expected_shortfall,
    )


@router.get("/portfolios/{portfolio_id}/sensitivities", response_model=list[SensitivityOut])
def portfolio_sensitivities(
    portfolio_id: int, db: Session = Depends(get_db)
) -> list[SensitivityOut]:
    """Sensibilidades (exposición USD y volatilidad anualizada) por posición."""
    try:
        profile = RiskService(db).profile(portfolio_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return [
        SensitivityOut(
            instrument=s.symbol,
            asset_class=s.asset_class,
            exposure=s.exposure,
            annualized_volatility=s.annualized_volatility,
        )
        for s in profile.sensitivities
    ]


class StressRequest(BaseModel):
    scenarios: dict[str, dict[str, float]] | None = None


@router.post("/portfolios/{portfolio_id}/stress", response_model=list[StressResultOut])
def portfolio_stress(
    portfolio_id: int,
    payload: StressRequest,
    db: Session = Depends(get_db),
) -> list[StressResultOut]:
    """Aplica shocks de precio por instrumento y devuelve el impacto en USD.

    Escenarios por defecto: caída de equities, rally, devaluación fx y spike de vol.
    """
    try:
        profile = RiskService(db).profile(
            portfolio_id, scenarios=payload.scenarios or SAMPLE_SCENARIOS
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return [
        StressResultOut(
            scenario_name=name,
            impact=result.impact,
            details=result.details,
        )
        for name, result in profile.stress.items()
    ]


@router.post("/portfolios/{portfolio_id}/report", response_model=RiskReport)
def portfolio_report(
    portfolio_id: int,
    params: VaRRequest,
    db: Session = Depends(get_db),
) -> RiskReport:
    """Reporte ejecutivo consolidado: VaR x método, stress y sensibilidades."""
    try:
        return ReportingService(db).build_report(
            portfolio_id,
            confidence_level=params.confidence_level,
            horizon_days=params.horizon_days,
            lookback_days=params.lookback_days,
            n_simulations=params.n_simulations,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))