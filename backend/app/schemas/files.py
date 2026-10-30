from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FileErrorDetail(BaseModel):
    code: str
    message: str


class UploadedFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    stored_filename: str
    file_type: str
    mime_type: str | None
    size_bytes: int
    uploaded_at: datetime
    processing_status: str
    error_message: str | None = None
    storage_key: str = Field(description="Relative storage reference, not a host filesystem path.")


class UploadedFileListResponse(BaseModel):
    items: list[UploadedFileResponse]
