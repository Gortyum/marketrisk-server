"""Adapter fino: lee posiciones y precios de la base y delega en el núcleo puro.

TODO el cálculo de riesgo vive en `app/risk/` (módulos puros). Esta clase
solo materializa los datos (posiciones, series de precios, exposiciones) y
los entrega al núcleo; no conoce la matemática del VaR.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.market_data import Instrument, PriceHistory
from app.models.portfolio import Portfolio, Position
from app.risk.metrics import log_returns
from app.risk.portfolio_profile import PortfolioProfile, portfolio_risk_profile
from app.risk.var import compute_var
from app.schemas.risk import VaRResult


class InstrumentNotFoundError(Exception):
    pass


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