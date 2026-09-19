from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.etl.extractors import CSVExtractor, JsonExtractor
from app.etl.loaders import DatabaseLoader
from app.etl.transformers import MarketDataTransformer


@dataclass
class PipelineResult:
    source: str
    instruments_loaded: int
    price_rows_loaded: int
    rejected_rows: int
    warnings: list[str]


class ETLPipeline:
    """Orquestación ETL: extract -> transform -> load.

    Uso típico desde la API:

        result = ETLPipeline(session).run(filepath, asset_class="equity")
    """

    def __init__(self, session: Session):
        self.session = session

    def run(self, source: str | Path, **transform_defaults) -> PipelineResult:
        source = Path(source)
        ext_cls = JsonExtractor if source.suffix.lower() == ".json" else CSVExtractor
        extractor = ext_cls(source)

        raw = extractor.extract()
        transformed = MarketDataTransformer().transform(raw, **transform_defaults)
        loader = DatabaseLoader(self.session)
        n_instruments, n_prices = loader.load(
            transformed.instruments, transformed.prices
        )
        return PipelineResult(
            source=str(source),
            instruments_loaded=n_instruments,
            price_rows_loaded=n_prices,
            rejected_rows=transformed.rejected_rows,
            warnings=transformed.warnings,
        )