from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MetricReport(BaseModel):
    key: str
    label: str
    formula: str
    inputs: list[str]
    status: str  # COMPUTED | NOT_COMPUTABLE
    reason: str | None = None  # why NOT_COMPUTABLE (inputs unavailable)
    computed_count: int = 0
    skipped_count: int = 0
    skipped_reasons: dict[str, int] = {}
    min: float | None = None
    max: float | None = None
    mean: float | None = None


class SheetAnalysis(BaseModel):
    sheet_name: str
    status: str  # ANALYZED | SKIPPED
    reason: str | None = None  # why SKIPPED
    row_count: int = 0
    recognized_concepts: list[str] = []
    entity_column: str | None = None
    date_column: str | None = None
    metrics: list[MetricReport] = []
    warnings: list[str] = []
    preview_rows: list[dict] = []
    metrics_storage_key: str | None = None


class FundamentalAnalysisResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_id: str
    processing_result_id: str
    status: str
    created_at: datetime
    error_message: str | None = None
    worksheets: list[SheetAnalysis]
