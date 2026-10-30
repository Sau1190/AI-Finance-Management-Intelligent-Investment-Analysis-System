"""One market-data fetch attempt for one symbol.

A snapshot records what a provider returned at a point in time: which
provider, what was accepted, what was rejected and why, and where the full
bar history was stored. Failed fetches are stored too (status FAILED with an
error code), so a caller can see *why* data is missing instead of guessing.
Full bars live in a CSV under storage/market/ (referenced by storage key);
only a small preview is kept inline.
"""

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FetchStatus(str, enum.Enum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MarketDataSnapshot(Base):
    __tablename__ = "market_data_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    history: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    bar_count: Mapped[int] = mapped_column(default=0, nullable=False)
    first_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    last_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rejected_bars: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    preview_bars: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    bars_storage_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
