from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PriceBar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class MarketDataSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    symbol: str
    provider: str
    history: str
    status: str
    created_at: datetime
    error_code: str | None = None
    error_message: str | None = None
    bar_count: int = 0
    first_date: str | None = None
    last_date: str | None = None
    rejected_bars: dict[str, int] = {}
    preview_bars: list[PriceBar] = []
    bars_storage_key: str | None = None


class PricesResponse(BaseModel):
    symbol: str
    snapshot_id: str
    provider: str
    fetched_at: datetime
    total_bars: int
    returned_bars: int
    bars: list[PriceBar]
