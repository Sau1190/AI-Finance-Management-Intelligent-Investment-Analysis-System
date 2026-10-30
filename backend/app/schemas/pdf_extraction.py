from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TableExtract(BaseModel):
    table_index: int
    row_count: int
    column_count: int
    preview_rows: list[list[str | None]] = []
    storage_key: str | None = None


class PageExtract(BaseModel):
    page_number: int
    char_count: int
    text_preview: str = ""
    text_storage_key: str | None = None
    table_count: int = 0
    tables: list[TableExtract] = []
    warnings: list[str] = []


class PdfExtractionResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_id: str
    status: str
    created_at: datetime
    error_message: str | None = None
    page_count: int = 0
    pages: list[PageExtract]
