"""Phase 11 orchestration: build the What-How-Why explanation of the latest
stored score for a symbol.

The explanation is derived on demand from the stored score (which already
carries its inputs, weights, and a snapshot of the method), so it is always
consistent with that score and nothing new is persisted. Only COMPLETE scores
can be explained; a FAILED score has no explanation to give.
"""

from sqlalchemy.orm import Session

from app.core.exceptions import AnalysisRequestError
from app.models.score_result import ScoreRunStatus
from app.services import explanation_builder, score_service


def _to_dict(record) -> dict:
    return {
        "id": record.id,
        "symbol": record.symbol,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "scoring_version": record.scoring_version,
        "notice": record.notice,
        "weights": record.weights,
        "weights_customised": record.weights_customised,
        "overall": record.overall,
        "components": record.components,
        "warnings": record.warnings,
        "method": record.method,
    }


def get_explanation(db: Session, symbol: str) -> dict | None:
    """The explanation of the latest score for `symbol`, or None if the symbol
    has never been scored. Raises a 409 request error if the latest score is
    a FAILED run.
    """
    record = score_service.get_latest_result(db, symbol)
    if record is None:
        return None
    if record.status != ScoreRunStatus.COMPLETE.value:
        raise AnalysisRequestError(
            "SCORE_NOT_COMPLETE",
            "The latest score for this symbol did not complete, so there is nothing to explain. "
            "Run the score again.",
            status_code=409,
        )
    return explanation_builder.build_explanation(_to_dict(record))
