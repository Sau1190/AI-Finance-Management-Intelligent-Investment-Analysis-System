"""Orchestrate file intake: validate → store → record metadata.

Phase 1 does not parse Excel/PDF contents for analysis.
"""

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import check_database_connection
from app.core.exceptions import FileIntakeError
from app.models.uploaded_file import ProcessingStatus, UploadedFile
from app.services import file_storage, file_validation


def ingest_upload(
    db: Session,
    *,
    filename: str | None,
    content_type: str | None,
    content: bytes,
) -> UploadedFile:
    db_status = check_database_connection()
    if not db_status["connected"]:
        raise FileIntakeError(
            "DATABASE_FAILURE",
            "File metadata could not be saved because the database is unavailable.",
            status_code=503,
        )

    meta = file_validation.validate_upload(
        filename=filename,
        content_type=content_type,
        content=content,
    )
    stored_filename, storage_key = file_storage.save_original_bytes(content, meta["file_type"])

    record = UploadedFile(
        original_filename=meta["original_filename"],
        stored_filename=stored_filename,
        file_type=meta["file_type"],
        mime_type=meta["mime_type"],
        size_bytes=meta["size_bytes"],
        processing_status=ProcessingStatus.VALIDATING.value,
        storage_key=storage_key,
    )
    try:
        db.add(record)
        db.flush()
        record.processing_status = ProcessingStatus.READY.value
        db.commit()
        db.refresh(record)
        return record
    except SQLAlchemyError as exc:
        db.rollback()
        file_storage.delete_stored_file(stored_filename)
        raise FileIntakeError(
            "DATABASE_FAILURE",
            "The file was not accepted because metadata could not be saved.",
            status_code=503,
        ) from exc


def get_file(db: Session, file_id: str) -> UploadedFile:
    record = db.get(UploadedFile, file_id)
    if record is None:
        raise FileIntakeError("FILE_NOT_FOUND", "No file was found for that id.", status_code=404)
    return record


def list_files(db: Session, limit: int = 20) -> list[UploadedFile]:
    statement = select(UploadedFile).order_by(UploadedFile.uploaded_at.desc()).limit(limit)
    return list(db.scalars(statement))
