"""Phase 7 technical analysis API. Thin routes — the work lives in
app.services.technical_service and technical_report.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppError
from app.schemas.technical import TechnicalAnalysisResultResponse, TechnicalSeriesResponse
from app.services import technical_service

router = APIRouter(prefix="/technical", tags=["technical"])


def _raise_http(exc: AppError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.post("/{symbol}", response_model=TechnicalAnalysisResultResponse, status_code=201)
def run_technical_analysis(symbol: str, db: Session = Depends(get_db)) -> TechnicalAnalysisResultResponse:
    """Compute indicators from the symbol's latest successful market-data
    fetch. A run that cannot produce results (too few bars, data file gone,
    storage failure) still returns 201 with status=FAILED and an error code.
    400 for an invalid symbol; 404 if no market data has been fetched.
    """
    try:
        result = technical_service.analyze_technical(db, symbol)
    except AppError as exc:
        _raise_http(exc)
    return TechnicalAnalysisResultResponse.model_validate(result)


@router.get("/{symbol}", response_model=TechnicalAnalysisResultResponse)
def get_technical_result(symbol: str, db: Session = Depends(get_db)) -> TechnicalAnalysisResultResponse:
    """The most recent technical-analysis run for a symbol (successful or not)."""
    try:
        result = technical_service.get_latest_result(db, symbol)
    except AppError as exc:
        _raise_http(exc)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "TECHNICAL_RESULT_NOT_FOUND",
                "message": "No technical analysis has been run for this symbol yet.",
            },
        )
    return TechnicalAnalysisResultResponse.model_validate(result)


@router.get("/{symbol}/series", response_model=TechnicalSeriesResponse)
def get_technical_series(
    symbol: str,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> TechnicalSeriesResponse:
    """The most recent `limit` rows of indicator values (ascending by date)
    from the latest successful run. A null means the indicator has no value on
    that date (warm-up or undefined).
    """
    try:
        result, total, rows = technical_service.read_series(db, symbol, limit)
    except AppError as exc:
        _raise_http(exc)
    return TechnicalSeriesResponse(
        symbol=result.symbol,
        result_id=result.id,
        market_snapshot_id=result.market_snapshot_id,
        total_rows=total,
        returned_rows=len(rows),
        rows=rows,
    )
