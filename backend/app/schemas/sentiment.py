from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated

SubmittedText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class SentimentTextsRequest(BaseModel):
    texts: list[SubmittedText] = Field(min_length=1, max_length=100)


class SentimentMatch(BaseModel):
    term: str
    weight: int
    negated: bool
    contribution: int


class SentimentItem(BaseModel):
    index: int
    text: str
    text_truncated: bool = False
    source: str | None = None
    published_at: str | None = None
    url: str | None = None
    score: float | None = None
    label: str
    positive: float = 0.0
    negative: float = 0.0
    evidence: float = 0.0
    matches: list[SentimentMatch] = []


class SentimentResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    symbol: str
    source_type: str
    provider: str | None = None
    query: str | None = None
    status: str
    created_at: datetime
    error_code: str | None = None
    error_message: str | None = None
    lexicon_version: str
    received_count: int = 0
    duplicates_removed: int = 0
    skipped: dict[str, int] = {}
    text_count: int = 0
    scored_count: int = 0
    counts: dict[str, int] = {}
    coverage: float | None = None
    mean_score: float | None = None
    label: str = "no_signal"
    earliest_published: str | None = None
    latest_published: str | None = None
    items: list[SentimentItem] = []
