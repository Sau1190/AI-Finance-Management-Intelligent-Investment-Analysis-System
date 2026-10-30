"""A PDF extraction run's structured result.

One row per extraction run of an uploaded PDF. Mirrors ProcessingResult's
shape: heavy structured detail (per-page text/table metadata) lives in a
JSON column — it is a report, not something later phases query relationally
yet. Analysis phases (5+) will read this to get validated, literal extracted
content; they must not re-guess or re-OCR what Phase 4 already determined.

Full extracted text and table data are NOT stored inline in this row (a
multi-page PDF's text could be large) — they are written to
storage/extracts/ with generated, non-overwriting names, same guarantee as
Phase 2's cleaned CSVs and Phase 3's exports. This row stores metadata plus
storage keys plus small bounded previews for API convenience.
"""

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ExtractionRunStatus(str, enum.Enum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PdfExtractionResult(Base):
    __tablename__ = "pdf_extraction_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("uploaded_files.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # One entry per page. Structure documented in docs/PDF_MODULE.md and
    # mirrored by app.schemas.pdf_extraction.PageExtract.
    pages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
