from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ExportResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_id: str
    processing_result_id: str
    status: str
    created_at: datetime
    error_message: str | None = None
    storage_key: str | None = None
    original_filename: str | None = None
    sheet_names: list[str] = []
