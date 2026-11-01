"""Phase 10 explainable-scoring API. Thin routes — the arithmetic lives in
app.services.scoring_engine and orchestration in score_service.

The score is an educational summary of already-computed indicators. Nothing
here is investment advice or a recommendation.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppError
from app.schemas.explanation import ExplanationResponse
from app.schemas.score import ScoreRequest, ScoreResultResponse
from app.services import explanation_service, score_service
from app.services import scoring_config

router = APIRouter(prefix="/scores", tags=["scores"])
method_router = APIRouter(tags=["scores"])


def _raise_http(exc: AppError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@method_router.get("/scoring-method")
def get_scoring_method() -> dict:
    """The complete scoring method: components, indicators, anchors, default
    weights, formulas, missing-data rules, and limits. Needs no data.
    """
    return scoring_config.describe_method()


@router.post("/{symbol}", response_model=ScoreResultResponse, status_code=201)
def compute_score(
    symbol: str, body: ScoreRequest | None = None, db: Session = Depends(get_db)
) -> ScoreResultResponse:
    """Score a symbol from the stored results of Phases 5, 7, 8 and 9. Optional
    body: `file_id` (+ `sheet_name`) to include fundamentals, and `weights` for
    the four components. A run that fails unexpectedly returns 201 with
    status=FAILED; a missing input is excluded and explained, not an error.
    400 for an invalid symbol/weights, 404 for an unknown file.
    """
    body = body or ScoreRequest()
    try:
        result = score_service.compute_score(
            db, symbol, file_id=body.file_id, sheet_name=body.sheet_name, weights=body.weights
        )
    except AppError as exc:
        _raise_http(exc)
    return ScoreResultResponse.model_validate(result)


@router.get("/{symbol}", response_model=ScoreResultResponse)
def get_score(symbol: str, db: Session = Depends(get_db)) -> ScoreResultResponse:
    """The most recent score for a symbol (successful or not)."""
    try:
        result = score_service.get_latest_result(db, symbol)
    except AppError as exc:
        _raise_http(exc)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "SCORE_RESULT_NOT_FOUND", "message": "No score has been computed for this symbol yet."},
        )
    return ScoreResultResponse.model_validate(result)


@router.get("/{symbol}/explanation", response_model=ExplanationResponse)
def get_score_explanation(symbol: str, db: Session = Depends(get_db)) -> ExplanationResponse:
    """What-How-Why explanation of the latest score for a symbol: what the
    score is, exactly how it was computed, and why it came out as it did. It is
    derived from the stored score (nothing is recomputed or invented) and is
    not advice. 404 if the symbol was never scored; 409 if its latest score
    run failed.
    """
    try:
        explanation = explanation_service.get_explanation(db, symbol)
    except AppError as exc:
        _raise_http(exc)
    if explanation is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "SCORE_RESULT_NOT_FOUND", "message": "No score has been computed for this symbol yet."},
        )
    return ExplanationResponse.model_validate(explanation)
