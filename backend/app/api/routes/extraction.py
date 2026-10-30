"""Phase 4 PDF extraction API. Thin routes — the pipeline lives in
app.services.pdf_extraction_service; this module only translates HTTP <->
service calls and turns AppError subclasses into HTTP responses.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppError, ExtractionRequestError, FileIntakeError
from app.schemas.pdf_extraction import PdfExtractionResultResponse
from app.services import file_service, pdf_extraction_service

router = APIRouter(prefix="/files/{file_id}/extract", tags=["extraction"])


def _raise_http(exc: AppError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.post("", response_model=PdfExtractionResultResponse, status_code=201)
def extract_file(file_id: str, db: Session = Depends(get_db)) -> PdfExtractionResultResponse:
    """Run the Phase 4 pipeline for an already-uploaded PDF. A PDF the
    pipeline cannot read (corrupt, encrypted, or too many pages) still
    returns 201 with status=FAILED on the result — that is a valid,
    inspectable outcome, not a server error.
    """
    try:
        uploaded_file = file_service.get_file(db, file_id)
    except FileIntakeError as exc:
        _raise_http(exc)

    try:
        result = pdf_extraction_service.extract_pdf(db, uploaded_file)
    except ExtractionRequestError as exc:
        _raise_http(exc)

    return PdfExtractionResultResponse.model_validate(result)


@router.get("", response_model=PdfExtractionResultResponse)
def get_extraction_result(file_id: str, db: Session = Depends(get_db)) -> PdfExtractionResultResponse:
    """Return the most recent extraction result for a file. 404 if the file
    itself does not exist, or if it exists but has never been extracted.
    """
    try:
        file_service.get_file(db, file_id)
    except FileIntakeError as exc:
        _raise_http(exc)

    result = pdf_extraction_service.get_latest_result(db, file_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "EXTRACTION_RESULT_NOT_FOUND", "message": "This file has not been extracted yet."},
        )
    return PdfExtractionResultResponse.model_validate(result)
