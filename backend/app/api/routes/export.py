"""Phase 3 export API. Thin routes — orchestration lives in
app.services.export_service; this module only translates HTTP <-> service
calls, including streaming the generated workbook back for download.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppError, FileIntakeError, ProcessingRequestError
from app.schemas.export import ExportResultResponse
from app.services import export_service, file_processing, file_service

router = APIRouter(prefix="/files/{file_id}/export", tags=["export"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _raise_http(exc: AppError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.post("", response_model=ExportResultResponse, status_code=201)
def export_file(file_id: str, db: Session = Depends(get_db)) -> ExportResultResponse:
    """Generate a formatted .xlsx export from the file's most recent
    processing result. 404 if the file has never been processed.
    """
    try:
        uploaded_file = file_service.get_file(db, file_id)
    except FileIntakeError as exc:
        _raise_http(exc)

    try:
        result = export_service.export_uploaded_file(db, uploaded_file)
    except ProcessingRequestError as exc:
        _raise_http(exc)

    return ExportResultResponse.model_validate(result)


@router.get("", response_model=ExportResultResponse)
def get_export_result(file_id: str, db: Session = Depends(get_db)) -> ExportResultResponse:
    """Return the most recent export's metadata. 404 if never exported."""
    try:
        file_service.get_file(db, file_id)
    except FileIntakeError as exc:
        _raise_http(exc)

    result = export_service.get_latest_export(db, file_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "EXPORT_NOT_FOUND", "message": "This file has not been exported yet."},
        )
    return ExportResultResponse.model_validate(result)


@router.get("/download")
def download_export(file_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """Stream the most recent successful export workbook's bytes."""
    try:
        file_service.get_file(db, file_id)
    except FileIntakeError as exc:
        _raise_http(exc)

    result = export_service.get_latest_export(db, file_id)
    if result is None or result.status != "COMPLETE" or not result.storage_key:
        raise HTTPException(
            status_code=404,
            detail={"code": "EXPORT_NOT_FOUND", "message": "No completed export is available for this file."},
        )

    path = file_processing.exports_directory() / Path(result.storage_key).name
    if not path.is_file():
        raise HTTPException(
            status_code=500,
            detail={"code": "EXPORT_FILE_MISSING", "message": "The export workbook could not be found in storage."},
        )

    return FileResponse(
        path,
        media_type=XLSX_MEDIA_TYPE,
        filename=result.original_filename or "export.xlsx",
    )
