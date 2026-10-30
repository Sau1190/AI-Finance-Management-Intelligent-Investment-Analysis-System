"""Phase 5 fundamental analysis API. Thin routes — the work lives in
app.services.fundamental_service and fundamental_metrics.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AnalysisRequestError, AppError, FileIntakeError
from app.schemas.fundamental import FundamentalAnalysisResultResponse
from app.services import file_service, fundamental_service

router = APIRouter(prefix="/files/{file_id}/fundamentals", tags=["fundamentals"])


def _raise_http(exc: AppError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.post("", response_model=FundamentalAnalysisResultResponse, status_code=201)
def run_fundamentals(file_id: str, db: Session = Depends(get_db)) -> FundamentalAnalysisResultResponse:
    """Compute fundamental metrics from the file's latest processing result.
    A run that cannot analyze anything still returns 201 with status=FAILED
    — an inspectable outcome, not a server error. 404 if the file does not
    exist or has never been processed.
    """
    try:
        uploaded_file = file_service.get_file(db, file_id)
    except FileIntakeError as exc:
        _raise_http(exc)

    try:
        result = fundamental_service.analyze_fundamentals(db, uploaded_file)
    except AnalysisRequestError as exc:
        _raise_http(exc)

    return FundamentalAnalysisResultResponse.model_validate(result)


@router.get("", response_model=FundamentalAnalysisResultResponse)
def get_fundamentals(file_id: str, db: Session = Depends(get_db)) -> FundamentalAnalysisResultResponse:
    """Return the most recent fundamental-analysis result for a file."""
    try:
        file_service.get_file(db, file_id)
    except FileIntakeError as exc:
        _raise_http(exc)

    result = fundamental_service.get_latest_result(db, file_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "FUNDAMENTAL_RESULT_NOT_FOUND",
                "message": "No fundamental analysis has been run for this file yet.",
            },
        )
    return FundamentalAnalysisResultResponse.model_validate(result)
