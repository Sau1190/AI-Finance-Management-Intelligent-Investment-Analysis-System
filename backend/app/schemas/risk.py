from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RiskMetricReport(BaseModel):
    key: str
    label: str
    description: str
    parameters: dict
    min_returns: int
    status: str  # COMPUTED | NOT_COMPUTABLE
    reason: str | None = None
    value: float | None = None
    details: dict = {}


class RiskAnalysisResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    symbol: str
    benchmark_symbol: str | None = None
    market_snapshot_id: str
    benchmark_snapshot_id: str | None = None
    status: str
    created_at: datetime
    error_code: str | None = None
    error_message: str | None = None
    bar_count: int = 0
    returns_count: int = 0
    first_date: str | None = None
    last_date: str | None = None
    metrics: list[RiskMetricReport] = []
    warnings: list[str] = []
