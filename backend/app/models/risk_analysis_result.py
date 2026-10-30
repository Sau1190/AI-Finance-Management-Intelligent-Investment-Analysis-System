"""One risk-analysis run for one symbol (optionally against a benchmark).

Records exactly which Phase 6 price snapshots were used (the asset's and, when
given, the benchmark's), so a result stays explainable after newer prices are
fetched. Everything is stored inline — the metric report is small — so there
are no file artifacts. Failed runs are stored with an error code.
"""

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RiskRunStatus(str, enum.Enum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RiskAnalysisResult(Base):
    __tablename__ = "risk_analysis_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    benchmark_symbol: Mapped[str | None] = mapped_column(String(16), nullable=True)
    market_snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("market_data_snapshots.id"), nullable=False
    )
    benchmark_snapshot_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("market_data_snapshots.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    bar_count: Mapped[int] = mapped_column(default=0, nullable=False)
    returns_count: Mapped[int] = mapped_column(default=0, nullable=False)
    first_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    last_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    metrics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
