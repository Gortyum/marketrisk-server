"""Genera datos de mercado sintéticos de muestra para la carpeta data/sample."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "data" / "sample"

INSTRUMENTS = [
    ("AAPL", "Apple Inc.", "equity", 185.0),
    ("MSFT", "Microsoft Corp.", "equity", 420.0),
    ("NVDA", "NVIDIA Corp.", "equity", 122.0),
    ("EURUSD", "EUR/USD spot", "fx", 1.09),
    ("XAU", "Gold spot", "commodity", 2450.0),
    ("UST10Y", "US Treasury 10Y", "rate", 4.2),
]

DAYS = 600
END = pd.Timestamp("2024-12-31")


def gen_series(seed: int, start: float, vol: float, drift: float = 0.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift / 252, vol / np.sqrt(252), DAYS - 1)
    return start * np.exp(np.concatenate([[0], np.cumsum(rets)]))


def main() -> None:
    rows = []
    for i, (symbol, name, asset_class, start) in enumerate(INSTRUMENTS):
        vol = { 0: 0.28, 1: 0.22, 2: 0.40, 3: 0.08, 4: 0.15, 5: 0.10 }[i]
        drift = { 0: 0.15, 1: 0.12, 2: 0.25, 3: 0.0, 4: 0.05, 5: 0.0 }[i]
        prices = gen_series(seed=100 + i, start=start, vol=vol, drift=drift)
        dates = pd.date_range(end=END, periods=DAYS, freq="B")
        for date, close in zip(dates, prices):
            rows.append({"symbol": symbol, "name": name, "date": date, "close": round(close, 4)})

    df = pd.DataFrame(rows)
    df.to_csv(f"{OUT}/sample_prices.csv", index=False)


if __name__ == "__main__":
    main()