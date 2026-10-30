"""Phase 8 sentiment API. Thin routes — scoring lives in
app.services.sentiment_engine and orchestration in sentiment_service.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import AppError
from app.schemas.sentiment import SentimentResultResponse, SentimentTextsRequest
from app.services import sentiment_service
from app.services.market_providers import ProviderError
from app.services.news_providers import NewsProvider, build_news_provider

router = APIRouter(prefix="/sentiment", tags=["sentiment"])


def _raise_http(exc: AppError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


def get_news_provider() -> NewsProvider:
    """Dependency: the configured news provider. 503 (nothing recorded) if none
    is configured — a server setup problem, not a fetch outcome. Tests replace
    this with a fake via app.dependency_overrides.
    """
    settings = get_settings()
    try:
        return build_news_provider(settings.news_provider, settings.news_api_key, settings.news_timeout_seconds)
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": exc.message}) from None


@router.post("/{symbol}/text", response_model=SentimentResultResponse, status_code=201)
def score_texts(
    symbol: str, body: SentimentTextsRequest, db: Session = Depends(get_db)
) -> SentimentResultResponse:
    """Score headlines/snippets you submit (1-100 texts, up to 2000 characters
    each). Needs no external service.
    """
    try:
        result = sentiment_service.score_submitted_texts(db, symbol, body.texts)
    except AppError as exc:
        _raise_http(exc)
    return SentimentResultResponse.model_validate(result)


@router.post("/{symbol}/news", response_model=SentimentResultResponse, status_code=201)
def score_news(
    symbol: str,
    query: str | None = Query(None, description="Search text; defaults to the symbol."),
    db: Session = Depends(get_db),
    provider: NewsProvider = Depends(get_news_provider),
) -> SentimentResultResponse:
    """Fetch recent English headlines from the configured news provider and
    score them. A provider problem is a 201 with status=FAILED and an error
    code; zero articles is a successful result with no score.
    """
    page_size = get_settings().news_page_size
    try:
        result = sentiment_service.fetch_and_score_news(db, symbol, query, provider, page_size)
    except AppError as exc:
        _raise_http(exc)
    return SentimentResultResponse.model_validate(result)


@router.get("/{symbol}", response_model=SentimentResultResponse)
def get_sentiment(
    symbol: str,
    source: Literal["text", "news"] | None = Query(None),
    db: Session = Depends(get_db),
) -> SentimentResultResponse:
    """The most recent sentiment result for a symbol (optionally for one source)."""
    try:
        result = sentiment_service.get_latest_result(db, symbol, source)
    except AppError as exc:
        _raise_http(exc)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "SENTIMENT_RESULT_NOT_FOUND", "message": "No sentiment analysis exists for this symbol yet."},
        )
    return SentimentResultResponse.model_validate(result)
