"""Phase 9 risk analysis API. Thin routes — the work lives in
app.services.risk_service and risk_report.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppError
from app.schemas.risk import RiskAnalysisResultResponse
from app.services import risk_service

router = APIRouter(prefix="/risk", tags=["risk"])


def _raise_http(exc: AppError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.post("/{symbol}", response_model=RiskAnalysisResultResponse, status_code=201)
def run_risk_analysis(
    symbol: str,
    benchmark: str | None = Query(None, description="Another symbol (fetched via /api/market-data) to measure beta against."),
    db: Session = Depends(get_db),
) -> RiskAnalysisResultResponse:
    """Compute market-risk metrics from the symbol's latest successful price
    fetch. A run that cannot produce results (too few bars, data file gone,
    unexpected error) still returns 201 with status=FAILED and an error code.
    400 for an invalid symbol or a benchmark equal to the symbol; 404 if the
    symbol's (or benchmark's) market data has not been fetched.
    """
    try:
        result = risk_service.analyze_risk(db, symbol, benchmark)
    except AppError as exc:
        _raise_http(exc)
    return RiskAnalysisResultResponse.model_validate(result)


@router.get("/{symbol}", response_model=RiskAnalysisResultResponse)
def get_risk_result(symbol: str, db: Session = Depends(get_db)) -> RiskAnalysisResultResponse:
    """The most recent risk-analysis run for a symbol (successful or not)."""
    try:
        result = risk_service.get_latest_result(db, symbol)
    except AppError as exc:
        _raise_http(exc)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RISK_RESULT_NOT_FOUND", "message": "No risk analysis has been run for this symbol yet."},
        )
    return RiskAnalysisResultResponse.model_validate(result)
