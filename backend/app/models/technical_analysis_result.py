"""One technical-indicator run for one symbol.

`market_snapshot_id` records exactly which Phase 6 price snapshot the
indicators were computed from, so a result stays explainable after newer
prices are fetched. Per-indicator detail lives in a JSON report; the full
per-bar indicator series lives in a CSV under storage/analysis/ (by storage
key). Failed runs are stored with an error code.
"""

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TechnicalRunStatus(str, enum.Enum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TechnicalAnalysisResult(Base):
    __tablename__ = "technical_analysis_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    market_snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("market_data_snapshots.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    bar_count: Mapped[int] = mapped_column(default=0, nullable=False)
    first_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    last_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    indicators: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    preview_rows: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    indicators_storage_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
