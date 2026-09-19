from collections import defaultdict
from typing import Iterable

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.market_data import Instrument, PriceHistory


class DatabaseLoader:
    """Carga datos transformados en la base (upsert por símbolo y por fecha).

    Un solo camino, un solo contrato: `prices` viene referenciado por símbolo
    (nunca por instrument_id). El dedupe es POR INSTRUMENTO: que una fecha ya
    exista para AAPL no descarta el mismo día para MSFT.
    """

    def __init__(self, session: Session):
        self.session = session

    def load(self, instruments: pd.DataFrame, prices: pd.DataFrame) -> tuple[int, int]:
        inst_map = self._upsert_instruments(instruments)
        existing_by_instrument = self._existing_dates_by_instrument()
        prices_inserted = 0

        for symbol, group in prices.groupby("symbol", sort=False):
            inst_id = inst_map[symbol]
            existing = existing_by_instrument.get(inst_id, set())
            new_rows = group[~group["date"].dt.date.isin(existing)]
            for chunk in self._chunkify(new_rows, 2000):
                self.session.add_all(
                    [
                        PriceHistory(
                            instrument_id=inst_id,
                            trade_date=row.date.date(),
                            close=float(row.close),
                        )
                        for row in chunk.itertuples(index=False)
                    ]
                )
                prices_inserted += len(chunk)

        self.session.commit()
        return len(instruments), prices_inserted

    def _upsert_instruments(self, instruments: pd.DataFrame) -> dict[str, int]:
        existing = {i.symbol: i.id for i in self.session.scalars(select(Instrument))}
        inst_map: dict[str, int] = {}
        for row in instruments.itertuples(index=False):
            if row.symbol in existing:
                inst_map[row.symbol] = existing[row.symbol]
                continue
            inst = Instrument(
                symbol=row.symbol,
                name=row.name,
                asset_class=row.asset_class,
                currency=row.currency,
            )
            self.session.add(inst)
            self.session.flush()  # asigna el id sin commit
            inst_map[row.symbol] = inst.id
        return inst_map

    def _existing_dates_by_instrument(self) -> dict[int, set]:
        """Fechas ya cargadas, agrupadas por instrumento (una sola query)."""
        out: dict[int, set] = defaultdict(set)
        for inst_id, trade_date in self.session.execute(
            select(PriceHistory.instrument_id, PriceHistory.trade_date)
        ):
            out[inst_id].add(trade_date)
        return out

    @staticmethod
    def _chunkify(df: pd.DataFrame, size: int) -> Iterable[pd.DataFrame]:
        for start in range(0, len(df), size):
            yield df.iloc[start : start + size]