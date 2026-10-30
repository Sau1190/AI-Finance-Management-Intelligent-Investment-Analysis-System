"""A generated Excel export run.

One row per export of an uploaded file's Phase 2 processing result. The
generated workbook itself lives in storage/exports/ (never the original
upload location); this row is the traceable record of that generation.
"""

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ExportRunStatus(str, enum.Enum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExportResult(Base):
    __tablename__ = "export_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("uploaded_files.id"), nullable=False, index=True)
    processing_result_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("processing_results.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sheet_names: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
