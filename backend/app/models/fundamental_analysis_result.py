"""A fundamental-analysis run's structured result.

One row per run. `processing_result_id` records exactly which Phase 2
processing run's cleaned data was analyzed, so a result stays explainable
even after the file is re-processed later. Per-worksheet detail (metric
definitions, inputs, computed/skipped counts, skip reasons) lives in a JSON
report; the full per-row metric values live in a generated CSV under
storage/analysis/ (referenced by storage key), not inline.
"""

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AnalysisRunStatus(str, enum.Enum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FundamentalAnalysisResult(Base):
    __tablename__ = "fundamental_analysis_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("uploaded_files.id"), nullable=False, index=True)
    processing_result_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("processing_results.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    worksheets: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
