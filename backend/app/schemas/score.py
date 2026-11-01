from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScoreRequest(BaseModel):
    file_id: str | None = Field(default=None, max_length=64, description="A processed + analysed file to take fundamentals from.")
    sheet_name: str | None = Field(default=None, max_length=255, description="Which analysed worksheet to use (needed if there are several).")
    weights: dict[str, float] | None = Field(
        default=None,
        description="Optional custom weights for fundamental, technical, sentiment, risk (all four; normalised to sum 1).",
    )


class IndicatorScore(BaseModel):
    key: str
    label: str
    note: str
    unit: str
    poor: float
    good: float
    direction: str
    status: str  # AVAILABLE | MISSING
    reason: str | None = None
    value: float | None = None
    sub_score: float | None = None
    saturated: str | None = None
    weight_in_component: float | None = None
    contribution_to_component: float | None = None


class ComponentScore(BaseModel):
    key: str
    label: str
    source: str
    status: str  # AVAILABLE | UNAVAILABLE
    reason: str | None = None
    score: float | None = None
    as_of: str | None = None
    source_ref: dict = {}
    warnings: list[str] = []
    min_indicators: int
    available_indicators: int
    total_indicators: int
    indicators: list[IndicatorScore] = []
    weight_configured: float | None = None
    weight_effective: float | None = None
    contribution_to_overall: float | None = None
    in_overall: bool = False


class OverallScore(BaseModel):
    score: float | None = None
    reason: str | None = None
    weight_coverage: float = 0.0
    contributing_components: list[str] = []
    excluded_components: dict[str, str] = {}


class ScoreResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    symbol: str
    file_id: str | None = None
    sheet_name: str | None = None
    status: str
    created_at: datetime
    error_code: str | None = None
    error_message: str | None = None
    scoring_version: str
    notice: str
    weights: dict[str, float] = {}
    weights_customised: bool = False
    overall: OverallScore | None = None
    components: list[ComponentScore] = []
    warnings: list[str] = []
    method: dict = {}
