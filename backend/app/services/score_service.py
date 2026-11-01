"""Orchestrates Phase 10: gather the stored results of earlier phases, score
them with app.services.scoring_engine, and persist the full explanation.

Rules (consistent with the rest of the project):
  * Inputs are only what earlier phases stored; nothing is fetched or recomputed.
  * Missing inputs are excluded with a recorded reason, never filled in.
  * The result carries a snapshot of the method and the weights used, plus the
    ids of the source results, so it can be reproduced and audited.
  * Nothing here recommends an action; the score is a summary of indicators
    against fixed reference ranges (see scoring_config.LIMITS).
  * An unexpected error is a FAILED result (only the exception type is logged);
    invalid weights / unknown file are request errors and record nothing.
"""

import logging

from sqlalchemy.orm import Session

from app.core.exceptions import AnalysisRequestError
from app.models.score_result import ScoreResult, ScoreRunStatus
from app.services import file_service, market_service, scoring_config as cfg, scoring_engine, scoring_inputs

logger = logging.getLogger(__name__)


def _consistency_warnings(components: list[dict]) -> list[str]:
    warnings: list[str] = []
    by_key = {c["key"]: c for c in components}
    tech, risk = by_key["technical"], by_key["risk"]
    if tech["status"] == "AVAILABLE" and risk["status"] == "AVAILABLE":
        a = tech["source_ref"].get("market_snapshot_id")
        b = risk["source_ref"].get("market_snapshot_id")
        if a != b:
            warnings.append(
                "The technical and risk inputs were computed from different market-data snapshots; "
                "re-run them on the same fetch if you want them aligned."
            )
    dates = {c["key"]: c["as_of"] for c in components if c["status"] == "AVAILABLE" and c["as_of"]}
    if len(set(dates.values())) > 1:
        warnings.append(
            "The inputs are as-of different dates ("
            + ", ".join(f"{k}: {v}" for k, v in dates.items())
            + "); the dates are reported but not reconciled."
        )
    if any(c["warnings"] for c in components):
        warnings.append("One or more inputs carry warnings; see components[].warnings.")
    return warnings


def compute_score(
    db: Session,
    symbol: str,
    *,
    file_id: str | None = None,
    sheet_name: str | None = None,
    weights: dict | None = None,
) -> ScoreResult:
    symbol = market_service.normalize_symbol(symbol)
    if sheet_name is not None and file_id is None:
        raise AnalysisRequestError(
            "SHEET_WITHOUT_FILE", "sheet_name can only be used together with file_id.", status_code=400
        )
    if file_id is not None:
        file_service.get_file(db, file_id)  # raises a 404 FILE_NOT_FOUND request error
    try:
        resolved_weights = scoring_engine.resolve_weights(weights)
    except ValueError as exc:
        raise AnalysisRequestError("INVALID_WEIGHTS", str(exc), status_code=400) from None

    fields: dict
    try:
        inputs = scoring_inputs.gather_all(db, symbol, file_id, sheet_name)
        built = scoring_engine.build_scores(inputs, weights)
        overall = built["overall"]
        fields = {
            "status": ScoreRunStatus.COMPLETE.value,
            "error_code": None,
            "error_message": None,
            "overall": overall,
            "overall_score": overall["score"],
            "weight_coverage": overall["weight_coverage"],
            "components": built["components"],
            "warnings": _consistency_warnings(built["components"]),
        }
    except Exception as exc:  # noqa: BLE001 — log the type only; never leave a half result
        logger.error("Scoring failed for %s: %s", symbol, type(exc).__name__)
        fields = {
            "status": ScoreRunStatus.FAILED.value,
            "error_code": "SCORING_FAILURE",
            "error_message": "The score could not be computed because of an unexpected error.",
            "overall": {},
            "overall_score": None,
            "weight_coverage": None,
            "components": [],
            "warnings": [],
        }

    record = ScoreResult(
        symbol=symbol,
        file_id=file_id,
        sheet_name=sheet_name,
        scoring_version=cfg.SCORING_VERSION,
        notice=cfg.NOTICE,
        weights=resolved_weights,
        weights_customised=weights is not None,
        method=cfg.describe_method(resolved_weights),
        **fields,
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        raise
    return record


def get_latest_result(db: Session, symbol: str) -> ScoreResult | None:
    symbol = market_service.normalize_symbol(symbol)
    return (
        db.query(ScoreResult)
        .filter(ScoreResult.symbol == symbol)
        .order_by(ScoreResult.created_at.desc())
        .first()
    )
