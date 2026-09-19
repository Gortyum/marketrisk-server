from datetime import date

from sqlalchemy import Date, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Instrument(Base):
    """Instrumento financiero (factor de riesgo primario)."""

    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    asset_class: Mapped[str] = mapped_column(String(32), index=True)  # equity, fx, rate, commodity
    currency: Mapped[str] = mapped_column(String(8), default="USD")

    prices: Mapped[list["PriceHistory"]] = relationship(
        back_populates="instrument", cascade="all, delete-orphan"
    )


class PriceHistory(Base):
    """Serie histórica diaria de precios (close) por instrumento."""

    __tablename__ = "price_history"
    __table_args__ = (UniqueConstraint("instrument_id", "trade_date", name="uq_price_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    close: Mapped[float] = mapped_column(Float)

    instrument: Mapped["Instrument"] = relationship(back_populates="prices")