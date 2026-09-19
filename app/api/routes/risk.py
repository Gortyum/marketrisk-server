"""Endpoints de análisis y reporte de riesgo de mercado.

Cada endpoint corta una vista del `RiskProfile` que produce el núcleo puro
de riesgo; ninguno vuelve a calcular nada por su cuenta.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.risk import SAMPLE_SCENARIOS
from app.schemas.risk import (
    FactorDecompositionOut,
    RiskReport,
    SensitivityOut,
    StressReportOut,
    StressReportRequest,
    StressResultOut,
    VaREngineRequest,
    VaREngineResult,
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


@router.post("/portfolios/{portfolio_id}/var/engine", response_model=VaREngineResult)
def portfolio_var_engine(
    portfolio_id: int,
    params: VaREngineRequest,
    db: Session = Depends(get_db),
) -> VaREngineResult:
    """Motor central: VaR + ES por segmento/confianza/horizonte con trazabilidad."""
    try:
        return RiskService(db).var_engine(
            portfolio_id,
            segment=params.segment,
            confidence_level=params.confidence_level,
            horizon_days=params.horizon_days,
            lookback_days=params.lookback_days,
            method=params.method.value,
            n_simulations=params.n_simulations,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/portfolios/{portfolio_id}/var/factors", response_model=FactorDecompositionOut
)
def portfolio_var_factors(
    portfolio_id: int,
    confidence_level: float = Query(default=0.95, gt=0.5, lt=1.0),
    horizon_days: int = Query(default=1, ge=1, le=30),
    lookback_days: int = Query(default=252, ge=30),
    db: Session = Depends(get_db),
) -> FactorDecompositionOut:
    """Contribución al VaR por factor y clase (Euler allocation sobre la covarianza)."""
    try:
        d = RiskService(db).decompose(
            portfolio_id,
            confidence_level=confidence_level,
            horizon_days=horizon_days,
            lookback_days=lookback_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return FactorDecompositionOut(
        target=d.portfolio_name,
        portfolio_value=round(d.market_value, 2),
        total_var=round(d.total_var, 2),
        confidence_level=d.confidence_level,
        horizon_days=d.horizon_days,
        method=d.method,
        classes=[
            {"asset_class": c.asset_class, "exposure": round(c.exposure, 2),
             "contribution": round(c.contribution, 2), "share": round(c.share, 6)}
            for c in d.classes
        ],
        factors=[
            {
                "symbol": f.symbol, "asset_class": f.asset_class,
                "exposure": round(f.exposure, 2),
                "annualized_volatility": round(f.annualized_volatility, 6),
                "delta": round(f.delta, 2), "gamma": round(f.gamma, 2),
                "vega": round(f.vega, 2), "contribution": round(f.contribution, 2),
                "share": round(f.share, 6),
            }
            for f in d.factors
        ],
    )


@router.post("/portfolios/{portfolio_id}/stress/report", response_model=StressReportOut)
def portfolio_stress_report(
    portfolio_id: int,
    params: StressReportRequest,
    db: Session = Depends(get_db),
) -> StressReportOut:
    """Estrés de un escenario: baseline vs. estresado (valor, P&L y VaR)."""
    try:
        return RiskService(db).stress_report(
            portfolio_id,
            scenario_name=params.scenario_name,
            shocks=params.shocks,
            confidence_level=params.confidence_level,
            horizon_days=params.horizon_days,
            lookback_days=params.lookback_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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