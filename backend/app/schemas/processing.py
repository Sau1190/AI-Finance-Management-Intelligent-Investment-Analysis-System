from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ColumnReport(BaseModel):
    name: str
    inferred_type: str
    missing_count: int
    canonical_concept: str | None = None
    inconsistent_values: dict | None = None


class AmbiguousMapping(BaseModel):
    canonical_concept: str
    source_columns: list[str]


class WorksheetReport(BaseModel):
    sheet_name: str
    is_empty: bool
    header_row_index: int | None = None
    header_assumed_default: bool = False
    row_count: int = 0
    column_count: int = 0
    columns: list[ColumnReport] = []
    duplicate_row_count: int = 0
    normalization_mappings: dict[str, str] = {}
    ambiguous_mappings: list[AmbiguousMapping] = []
    warnings: list[str] = []
    errors: list[str] = []
    cleaned_data_status: str
    cleaned_data_storage_key: str | None = None
    csv_delimiter: str | None = None


class ProcessingResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_id: str
    status: str
    created_at: datetime
    error_message: str | None = None
    worksheets: list[WorksheetReport]
