"""One explainable-score run for one symbol.

Stores the complete explanation, not just the number: every component and
indicator with its input value, anchors, sub-score, weight and contribution,
the ids of the earlier-phase results it was built from, the weights that were
used, and a SNAPSHOT of the scoring method (anchors, rules, limits) so a stored
score stays reproducible and explainable even if the configuration changes
later. Results are stored inline; there are no file artifacts.
"""

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ScoreRunStatus(str, enum.Enum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScoreResult(Base):
    __tablename__ = "score_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    file_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("uploaded_files.id"), nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    scoring_version: Mapped[str] = mapped_column(String(16), nullable=False)
    notice: Mapped[str] = mapped_column(Text, nullable=False, default="")
    weights: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    weights_customised: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    overall: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    components: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    method: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
