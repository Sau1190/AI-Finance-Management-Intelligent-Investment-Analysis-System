"""Phase 2 processing API. Thin routes — the pipeline lives in
app.services.processing_service; this module only translates HTTP <->
service calls and turns AppError subclasses into HTTP responses.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppError, FileIntakeError, ProcessingRequestError
from app.schemas.processing import ProcessingResultResponse
from app.services import file_service, processing_service

router = APIRouter(prefix="/files/{file_id}/process", tags=["processing"])


def _raise_http(exc: AppError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.post("", response_model=ProcessingResultResponse, status_code=201)
def process_file(file_id: str, db: Session = Depends(get_db)) -> ProcessingResultResponse:
    """Run the Phase 2 pipeline for an already-uploaded file. A file the
    pipeline cannot parse still returns 201 with status=FAILED on the
    result — that is a valid, inspectable outcome, not a server error.
    """
    try:
        uploaded_file = file_service.get_file(db, file_id)
    except FileIntakeError as exc:
        _raise_http(exc)

    try:
        result = processing_service.process_uploaded_file(db, uploaded_file)
    except ProcessingRequestError as exc:
        _raise_http(exc)

    return ProcessingResultResponse.model_validate(result)


@router.get("", response_model=ProcessingResultResponse)
def get_processing_result(file_id: str, db: Session = Depends(get_db)) -> ProcessingResultResponse:
    """Return the most recent processing result for a file. 404 if the file
    itself does not exist, or if it exists but has never been processed.
    """
    try:
        file_service.get_file(db, file_id)
    except FileIntakeError as exc:
        _raise_http(exc)

    result = processing_service.get_latest_result(db, file_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROCESSING_RESULT_NOT_FOUND", "message": "This file has not been processed yet."},
        )
    return ProcessingResultResponse.model_validate(result)
