"""One sentiment-analysis run for one symbol.

Every score is explainable: `items` holds, per text, the exact lexicon terms
that produced it. `lexicon_version` records which word list was used so a
stored result can always be reproduced. Results are stored inline (bounded by
the maximum text count) — no separate file artifacts.
"""

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SentimentRunStatus(str, enum.Enum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SentimentResult(Base):
    __tablename__ = "sentiment_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(8), nullable=False)  # "text" | "news"
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    query: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    lexicon_version: Mapped[str] = mapped_column(String(16), nullable=False)
    received_count: Mapped[int] = mapped_column(default=0, nullable=False)
    duplicates_removed: Mapped[int] = mapped_column(default=0, nullable=False)
    skipped: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    text_count: Mapped[int] = mapped_column(default=0, nullable=False)
    scored_count: Mapped[int] = mapped_column(default=0, nullable=False)
    counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    label: Mapped[str] = mapped_column(String(16), nullable=False, default="no_signal")
    earliest_published: Mapped[str | None] = mapped_column(String(32), nullable=True)
    latest_published: Mapped[str | None] = mapped_column(String(32), nullable=True)
    items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
