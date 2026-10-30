from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IndicatorReport(BaseModel):
    key: str
    label: str
    description: str
    parameters: dict
    min_bars: int
    status: str  # COMPUTED | NOT_COMPUTABLE
    reason: str | None = None
    warmup_rows: int = 0
    computed_count: int = 0
    undefined_rows: int = 0
    min: float | None = None
    max: float | None = None
    latest: float | None = None
    latest_date: str | None = None


class TechnicalAnalysisResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    symbol: str
    market_snapshot_id: str
    status: str
    created_at: datetime
    error_code: str | None = None
    error_message: str | None = None
    bar_count: int = 0
    first_date: str | None = None
    last_date: str | None = None
    indicators: list[IndicatorReport] = []
    preview_rows: list[dict] = []
    indicators_storage_key: str | None = None


class TechnicalSeriesResponse(BaseModel):
    symbol: str
    result_id: str
    market_snapshot_id: str
    total_rows: int
    returned_rows: int
    rows: list[dict]
