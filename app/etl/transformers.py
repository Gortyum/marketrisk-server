from dataclasses import dataclass, field

import pandas as pd

from app.config import settings


@dataclass
class TransformResult:
    instruments: pd.DataFrame  # columnas: symbol, name, asset_class, currency
    prices: pd.DataFrame       # columnas: symbol, date, close
    rejected_rows: int = 0
    warnings: list[str] = field(default_factory=list)


class MarketDataTransformer:
    """Limpia y valida datos de mercado antes de cargarlos a la base.

    Ahora la transformación elimina duplicados, rellena fechas faltantes con
    forward-fill (útil para series con feriados) y valida precios no negativos.
    """

    def __init__(
        self,
        max_missing_ratio: float = settings.max_missing_ratio,
        negative_price_allowed: bool = settings.negative_price_allowed,
    ):
        self.max_missing_ratio = max_missing_ratio
        self.negative_price_allowed = negative_price_allowed

    def transform(self, raw: pd.DataFrame, **defaults) -> TransformResult:
        df = raw.copy()
        rejected = 0
        warnings: list[str] = []

        # 1. Tipos básicos.
        df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")

        # 2. Rechazar filas sin símbolo, sin fecha válida o con precio inválido.
        mask_valid = df["symbol"].ne("") & df["date"].notna() & df["close"].notna()
        if not self.negative_price_allowed:
            mask_valid &= df["close"].gt(0)
        rejected += int((~mask_valid).sum())
        df = df.loc[mask_valid].copy()
        if not df.shape[0]:
            raise ValueError("No hay filas válidas después de la validación inicial.")

        # 3. Eliminar filas totalmente duplicadas.
        df = df.drop_duplicates(subset=["symbol", "date"])

        # 4. Metadata de instrumentos.
        instrument_defaults = {
            "name": "Unknown",
            "asset_class": "equity",
            "currency": "USD",
        }
        instrument_defaults.update(defaults)
        instruments = (
            df.groupby("symbol")
            .first()
            .reset_index()[["symbol"]]
            .assign(
                name=lambda d: d.get("name", instrument_defaults["name"]),
                asset_class=instrument_defaults["asset_class"],
                currency=instrument_defaults["currency"],
            )
        )
        if "name" in df.columns:
            names = df.drop_duplicates("symbol").set_index("symbol")["name"]
            instruments["name"] = instruments["symbol"].map(names).fillna(instrument_defaults["name"])

        # 5. Rellenar fechas faltantes con forward-fill por símbolo,
        #    descartando series con demasiados huecos.
        prices = df[["symbol", "date", "close"]].sort_values(["symbol", "date"])
        filled = []
        for symbol, group in prices.groupby("symbol", sort=False):
            group = group.set_index("date").asfreq("D")
            missing = int(group["close"].isna().sum())
            ratio = missing / len(group) if len(group) else 0.0
            if ratio > self.max_missing_ratio:
                warnings.append(f"{symbol}: {ratio:.0%} de fechas faltantes, serie descartada.")
                continue
            group = group.ffill().dropna().reset_index()
            group["symbol"] = symbol
            filled.append(group)
        prices = pd.concat(filled, ignore_index=True) if filled else prices.iloc[0:0].copy()

        if prices.empty:
            raise ValueError("Ninguna serie de precios sobrevivió a la transformación.")

        instruments = instruments[instruments["symbol"].isin(prices["symbol"].unique())]

        return TransformResult(
            instruments=instruments[["symbol", "name", "asset_class", "currency"]],
            prices=prices[["symbol", "date", "close"]],
            rejected_rows=rejected,
            warnings=warnings,
        )