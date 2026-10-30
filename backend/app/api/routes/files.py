"""File intake API. Thin routes — validation and storage live in services."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import FileIntakeError
from app.schemas.files import UploadedFileListResponse, UploadedFileResponse
from app.services import file_service

router = APIRouter(prefix="/files", tags=["files"])


def _raise_http(exc: FileIntakeError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.post("", response_model=UploadedFileResponse, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadedFileResponse:
    content = await file.read()
    try:
        record = file_service.ingest_upload(
            db,
            filename=file.filename,
            content_type=file.content_type,
            content=content,
        )
    except FileIntakeError as exc:
        _raise_http(exc)
    return UploadedFileResponse.model_validate(record)


@router.get("", response_model=UploadedFileListResponse)
def list_uploaded_files(db: Session = Depends(get_db)) -> UploadedFileListResponse:
    items = file_service.list_files(db)
    return UploadedFileListResponse(items=[UploadedFileResponse.model_validate(item) for item in items])


@router.get("/{file_id}", response_model=UploadedFileResponse)
def get_uploaded_file(file_id: str, db: Session = Depends(get_db)) -> UploadedFileResponse:
    try:
        record = file_service.get_file(db, file_id)
    except FileIntakeError as exc:
        _raise_http(exc)
    return UploadedFileResponse.model_validate(record)
