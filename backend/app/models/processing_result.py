"""A processing run's structured data-quality report.

One row per processing run of an uploaded file. The heavy structured detail
(per-worksheet columns, missing-value counts, mappings, findings) lives in
JSON columns — it is a report, not something later phases query relationally
yet. Analysis phases (5+) will read this to get a validated, explainable
starting point; they must not re-guess what Phase 2 already determined.
"""

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProcessingRunStatus(str, enum.Enum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProcessingResult(Base):
    __tablename__ = "processing_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("uploaded_files.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # One entry per worksheet (XLSX) or a single synthetic entry named "csv".
    # Structure is documented in docs/EXCEL_MODULE.md and mirrored by
    # app.schemas.processing.WorksheetReport.
    worksheets: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
