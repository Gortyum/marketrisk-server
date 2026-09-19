"""Adapter fino: lee posiciones y precios de la base y delega en el núcleo puro.

TODO el cálculo de riesgo vive en `app/risk/` (módulos puros). Esta clase
solo materializa los datos (posiciones, series de precios, exposiciones) y
los entrega al núcleo; no conoce la matemática del VaR.
"""
from __future__ import annotations

from time import perf_counter

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.market_data import Instrument, PriceHistory
from app.models.portfolio import Portfolio, Position
from app.risk.metrics import log_returns
from app.risk.portfolio_profile import (
    FactorDecomposition,
    PortfolioProfile,
    factor_decomposition,
    portfolio_risk_profile,
)
from app.risk.var import compute_var
from app.schemas.risk import StressReportOut, VaREngineResult, VaRResult


class InstrumentNotFoundError(Exception):
    pass


SEGMENT_ASSET_CLASS = {
    "all": None,
    "fx": "fx",
    "equity": "equity",
    "commodity": "commodity",
    "rate": "rate",
}


class RiskService:
    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------ datos
    def _price_series(self, instrument_id: int, lookback: int) -> pd.Series:
        rows = self.session.execute(
            select(PriceHistory.trade_date, PriceHistory.close)
            .where(PriceHistory.instrument_id == instrument_id)
            .order_by(PriceHistory.trade_date)
        ).all()
        if not rows:
            raise InstrumentNotFoundError(instrument_id)
        s = pd.Series(
            {date: close for date, close in rows[-lookback:]},
            dtype=float,
        )
        return s.sort_index()

    def _positions(self, portfolio_id: int) -> list[Position]:
        return list(
            self.session.scalars(
                select(Position).where(Position.portfolio_id == portfolio_id)
            )
        )

    def _returns_matrix(self, positions: list[Position], lookback: int) -> pd.DataFrame:
        """Matriz de log-retornos por fecha; columnas = símbolo."""
        series = {}
        for pos in positions:
            prices = self._price_series(pos.instrument_id, lookback).to_numpy()
            symbol = self.session.get(Instrument, pos.instrument_id).symbol
            series[symbol] = log_returns(prices)
        return pd.DataFrame(series).dropna()

    def _exposures(self, positions: list[Position], lookback: int) -> dict[str, float]:
        out = {}
        for pos in positions:
            symbol = self.session.get(Instrument, pos.instrument_id).symbol
            last_price = float(self._price_series(pos.instrument_id, lookback).iloc[-1])
            out[symbol] = last_price * pos.quantity
        return out

    def _asset_classes(self, positions: list[Position]) -> dict[str, str]:
        return {
            self.session.get(Instrument, p.instrument_id).symbol: self.session.get(
                Instrument, p.instrument_id
            ).asset_class
            for p in positions
        }

    # ---------------------------------------------------------- perfil (seam)
    def profile(
        self,
        portfolio_id: int,
        *,
        confidence_level: float = 0.95,
        horizon_days: int = 1,
        lookback_days: int = 252,
        n_simulations: int = 10_000,
        seed: int = 42,
        scenarios: dict[str, dict[str, float]] | None = None,
    ) -> PortfolioProfile:
        """Perfil completo de riesgo del portafolio en un solo pase de datos."""
        portfolio = self.session.get(Portfolio, portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portafolio {portfolio_id} no encontrado.")
        positions = self._positions(portfolio_id)
        if not positions:
            raise ValueError("El portafolio no tiene posiciones.")

        returns = self._returns_matrix(positions, lookback_days)
        if returns.empty or returns.shape[1] != len(positions):
            raise ValueError("No hay retornos alineados suficientes para el portafolio.")

        return portfolio_risk_profile(
            portfolio.name,
            returns,
            self._exposures(positions, lookback_days),
            self._asset_classes(positions),
            confidence_level=confidence_level,
            horizon_days=horizon_days,
            n_simulations=n_simulations,
            seed=seed,
            scenarios=scenarios,
        )

    # ----------------------------------------------------------- motor central
    def var_engine(
        self,
        portfolio_id: int,
        *,
        segment: str = "all",
        confidence_level: float = 0.95,
        horizon_days: int = 1,
        lookback_days: int = 252,
        method: str = "historical",
        n_simulations: int = 10_000,
        seed: int = 42,
    ) -> VaREngineResult:
        """VaR + ES de un segmento, con trazabilidad del cálculo.

        Segmenta el portafolio por clase de activo, calcula la pérdida del
        portafolio (VaR/ES históricos) y devuelve también la peor pérdida
        observada y los metadatos del pipeline — observaciones, factores,
        posiciones, valor de mercado y tiempo — para que la cifra nunca se
        consuma huérfana.
        """
        t0 = perf_counter()
        portfolio = self.session.get(Portfolio, portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portafolio {portfolio_id} no encontrado.")
        positions = self._positions(portfolio_id)
        if not positions:
            raise ValueError("El portafolio no tiene posiciones.")

        asset_class = SEGMENT_ASSET_CLASS[segment]
        if asset_class is not None:
            selected = [
                p
                for p in positions
                if (inst := self.session.get(Instrument, p.instrument_id)) is not None
                and inst.asset_class == asset_class
            ]
            if not selected:
                raise ValueError(f"El segmento '{segment}' no tiene posiciones.")
            positions = selected

        returns = self._returns_matrix(positions, lookback_days)
        if returns.empty or returns.shape[1] != len(positions):
            raise ValueError("No hay retornos alineados suficientes para el segmento.")

        exposures = self._exposures(positions, lookback_days)
        total_value = sum(exposures.values())
        if total_value <= 0:
            raise ValueError("El valor del segmento es cero.")

        weights = np.array([exposures[s] / total_value for s in returns.columns])
        port_returns = returns.to_numpy() @ weights

        var_pct, es_pct = compute_var(
            port_returns,
            method,
            confidence_level,
            horizon_days,
            n_simulations,
            seed=seed,
        )
        worst_pct = float(max(-port_returns)) * np.sqrt(horizon_days)

        return VaREngineResult(
            target=portfolio.name,
            segment=segment,
            method=method,
            confidence_level=confidence_level,
            horizon_days=horizon_days,
            portfolio_value=round(total_value, 2),
            var_value=round(var_pct * total_value, 2),
            expected_shortfall=round(es_pct * total_value, 2),
            worst_historical_loss=round(worst_pct * total_value, 2),
            n_observations=int(len(port_returns)),
            n_factors=len(exposures),
            n_positions=len(positions),
            calculation_time_ms=round((perf_counter() - t0) * 1000, 2),
        )

    # ------------------------------------------------------------ descomposición
    def decompose(
        self,
        portfolio_id: int,
        *,
        confidence_level: float = 0.95,
        horizon_days: int = 1,
        lookback_days: int = 252,
        method: str = "historical",
    ) -> FactorDecomposition:
        """Contribución al VaR por factor y por clase (Euler allocation)."""
        portfolio = self.session.get(Portfolio, portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portafolio {portfolio_id} no encontrado.")
        positions = self._positions(portfolio_id)
        if not positions:
            raise ValueError("El portafolio no tiene posiciones.")

        returns = self._returns_matrix(positions, lookback_days)
        if returns.empty or returns.shape[1] != len(positions):
            raise ValueError("No hay retornos alineados suficientes para el portafolio.")

        return factor_decomposition(
            portfolio.name,
            returns,
            self._exposures(positions, lookback_days),
            self._asset_classes(positions),
            confidence_level=confidence_level,
            horizon_days=horizon_days,
            method=method,
        )

    # -------------------------------------------------------------- estrés
    def stress_report(
        self,
        portfolio_id: int,
        scenario_name: str,
        shocks: dict[str, float],
        *,
        confidence_level: float = 0.95,
        horizon_days: int = 1,
        lookback_days: int = 252,
    ) -> StressReportOut:
        """Baseline vs. escenario: valor, P&L y VaR antes/después del shock.

        - P&L = Σ exposición_i × shock_i (shocks con signo: -0.15 = -15%).
        - El VaR estresado hace entrar el escenario en la distribución
          histórica (se añade el retorno del escenario como una observación).
          Se escala por el valor baseline (no el estresado): el VaR es una
          métrica de riesgo del libro frente a la distribución estresada, y
          el P&L es quien refleja el impacto sobre el valor.
        """
        t0 = perf_counter()
        portfolio = self.session.get(Portfolio, portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portafolio {portfolio_id} no encontrado.")
        positions = self._positions(portfolio_id)
        if not positions:
            raise ValueError("El portafolio no tiene posiciones.")

        returns = self._returns_matrix(positions, lookback_days)
        if returns.empty or returns.shape[1] != len(positions):
            raise ValueError("No hay retornos alineados suficientes para el portafolio.")

        exposures = self._exposures(positions, lookback_days)
        total_value = sum(exposures.values())
        if total_value <= 0:
            raise ValueError("El valor del portafolio es cero.")

        pnl = sum(
            exposure * shocks.get(symbol, 0.0) for symbol, exposure in exposures.items()
        )
        stressed_value = total_value + pnl
        if stressed_value <= 0:
            raise ValueError("El escenario lleva el valor del portafolio a un nivel no positivo.")

        weights = np.array([exposures[s] / total_value for s in returns.columns])
        port_returns = returns.to_numpy() @ weights
        var_pct, _ = compute_var(
            port_returns, "historical", confidence_level, horizon_days
        )
        var_baseline = var_pct * total_value

        scenario_return = pnl / total_value
        stressed_returns = np.concatenate([port_returns, np.array([scenario_return])])
        var_spct, _ = compute_var(
            stressed_returns, "historical", confidence_level, horizon_days
        )
        var_stressed = var_spct * total_value

        return StressReportOut(
            scenario_name=scenario_name,
            baseline_value=round(total_value, 2),
            stressed_value=round(stressed_value, 2),
            pnl=round(pnl, 2),
            var_baseline=round(var_baseline, 2),
            var_stressed=round(var_stressed, 2),
            n_positions=len(positions),
        )

    # -------------------------------------------------------------- VaR single
    def var_for_instrument(
        self,
        instrument_id: int,
        *,
        confidence_level: float = 0.95,
        horizon_days: int = 1,
        lookback_days: int = 252,
        method: str,
        n_simulations: int = 10_000,
        seed: int = 42,
    ) -> VaRResult:
        """VaR (USD) para un instrumento individual: retornos -> compute_var."""
        inst = self.session.get(Instrument, instrument_id)
        prices = self._price_series(instrument_id, lookback_days).to_numpy()
        returns = log_returns(prices)
        var, es = compute_var(
            returns,
            method,
            confidence_level,
            horizon_days,
            n_simulations,
            seed=seed,
        )
        last_price = float(prices[-1])
        return VaRResult(
            target=inst.symbol,
            method=method,
            confidence_level=confidence_level,
            horizon_days=horizon_days,
            var_value=var * last_price,
            expected_shortfall=es * last_price,
        )