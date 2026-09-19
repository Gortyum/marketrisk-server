"""Endpoints de portafolios: creación y posiciones."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.market_data import Instrument
from app.models.portfolio import Portfolio, Position
from app.schemas.portfolio import (
    PortfolioCreate,
    PortfolioDetail,
    PortfolioOut,
    PositionCreate,
    PositionOut,
)

router = APIRouter(prefix="/portfolios", tags=["Portafolios"])


def _get_or_404(db: Session, model, id: int, label: str):
    obj = db.get(model, id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} {id} no existe.")
    return obj


@router.post("", response_model=PortfolioOut, status_code=201)
def create_portfolio(payload: PortfolioCreate, db: Session = Depends(get_db)) -> Portfolio:
    if db.scalars(select(Portfolio).where(Portfolio.name == payload.name)).first():
        raise HTTPException(status_code=409, detail="Ya existe un portafolio con ese nombre.")
    portfolio = Portfolio(name=payload.name)
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return portfolio


@router.get("", response_model=list[PortfolioOut])
def list_portfolios(db: Session = Depends(get_db)) -> list[Portfolio]:
    return list(db.scalars(select(Portfolio).order_by(Portfolio.name)))


@router.get("/{portfolio_id}", response_model=PortfolioDetail)
def get_portfolio(portfolio_id: int, db: Session = Depends(get_db)) -> PortfolioDetail:
    portfolio = _get_or_404(db, Portfolio, portfolio_id, "Portafolio")
    positions = list(
        db.scalars(select(Position).where(Position.portfolio_id == portfolio_id))
    )
    return PortfolioDetail(
        id=portfolio.id,
        name=portfolio.name,
        positions=[PositionOut.model_validate(p) for p in positions],
    )


@router.post("/{portfolio_id}/positions", response_model=PositionOut, status_code=201)
def add_position(
    portfolio_id: int,
    payload: PositionCreate,
    db: Session = Depends(get_db),
) -> Position:
    _get_or_404(db, Portfolio, portfolio_id, "Portafolio")
    _get_or_404(db, Instrument, payload.instrument_id, "Instrumento")
    position = Position(
        portfolio_id=portfolio_id,
        instrument_id=payload.instrument_id,
        quantity=payload.quantity,
        weight=payload.weight,
    )
    db.add(position)
    db.commit()
    db.refresh(position)
    return position