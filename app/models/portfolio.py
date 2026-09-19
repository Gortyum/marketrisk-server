from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Portfolio(Base):
    """Portafolio de posiciones."""

    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)


class Position(Base):
    """Posición de un instrumento dentro de un portafolio."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float)  # unidades / nocional
    weight: Mapped[float] = mapped_column(Float, default=1.0)  # peso relativo / nociónal