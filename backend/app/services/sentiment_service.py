"""Orchestrates Phase 8: gather texts (submitted, or fetched as news
headlines), score them deterministically, and record an explainable result.

Rules (consistent with the rest of the project):
  * Scoring is the lexicon engine only — no model, no LLM, nothing estimated.
    A text with no lexicon term has NO signal; it is not counted as neutral.
  * Exact duplicate texts (same words, ignoring case/spacing — typically a
    syndicated headline) are counted once, and how many were removed is
    reported. Articles with no usable text (e.g. NewsAPI's "[Removed]"
    placeholders) are skipped and counted, never scored.
  * A news-provider problem is a FAILED result with an error code, not a server
    error. Zero articles is a successful, empty result (mean_score null).
  * User-facing messages are authored here; raw provider text, URLs, and
    exception strings are never echoed or logged.
"""

import logging
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import AnalysisRequestError
from app.models.sentiment_result import SentimentResult, SentimentRunStatus
from app.services import market_service, sentiment_engine
from app.services import sentiment_lexicon as lex
from app.services.market_providers import ProviderError
from app.services.news_providers import NewsProvider

logger = logging.getLogger(__name__)

DISPLAY_CHARS = 300
MAX_URL_CHARS = 500
MAX_QUERY_CHARS = 100


def normalize_symbol(symbol: str) -> str:
    return market_service.normalize_symbol(symbol)


def normalize_query(query: str | None, symbol: str) -> str:
    if query is None:
        return symbol
    cleaned = query.strip()
    if not cleaned or len(cleaned) > MAX_QUERY_CHARS or not cleaned.isprintable():
        raise AnalysisRequestError(
            "INVALID_QUERY",
            f"The search query must be 1-{MAX_QUERY_CHARS} printable characters.",
            status_code=400,
        )
    return cleaned


def _clean(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _iso_utc(value) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _safe_url(value) -> str | None:
    url = _clean(value)
    if url.startswith(("http://", "https://")) and len(url) <= MAX_URL_CHARS:
        return url
    return None


def _candidates_from_articles(articles: list[dict]) -> tuple[list[dict], Counter]:
    candidates: list[dict] = []
    skipped: Counter = Counter()
    for article in articles:
        title = _clean(article.get("title"))
        if not title or title.lower() == "[removed]":
            skipped["no usable title"] += 1
            continue
        description = _clean(article.get("description"))
        if description.lower() == "[removed]":
            description = ""
        candidates.append(
            {
                "text": f"{title}. {description}" if description else title,
                "dedupe_key": sentiment_engine.normalize_for_dedup(title),
                "source": _clean(article.get("source")) or None,
                "published_at": _iso_utc(article.get("published_at")),
                "url": _safe_url(article.get("url")),
            }
        )
    return candidates, skipped


def _record(
    db: Session,
    *,
    symbol: str,
    source_type: str,
    provider: str | None,
    query: str | None,
    received_count: int,
    candidates: list[dict],
    skipped: Counter,
    error_code: str | None = None,
    error_message: str | None = None,
) -> SentimentResult:
    seen: set[str] = set()
    items: list[dict] = []
    duplicates = 0
    for candidate in candidates:
        if candidate["dedupe_key"] in seen:
            duplicates += 1
            continue
        seen.add(candidate["dedupe_key"])
        result = sentiment_engine.score_text(candidate["text"])
        text = candidate["text"]
        items.append(
            {
                "index": len(items),
                "text": text[:DISPLAY_CHARS],
                "text_truncated": len(text) > DISPLAY_CHARS,
                "source": candidate["source"],
                "published_at": candidate["published_at"],
                "url": candidate["url"],
                **result,
            }
        )

    summary = sentiment_engine.aggregate(items)
    published = sorted(i["published_at"] for i in items if i["published_at"])
    failed = error_code is not None
    record = SentimentResult(
        symbol=symbol,
        source_type=source_type,
        provider=provider,
        query=query,
        status=(SentimentRunStatus.FAILED if failed else SentimentRunStatus.COMPLETE).value,
        error_code=error_code,
        error_message=error_message,
        lexicon_version=lex.LEXICON_VERSION,
        received_count=received_count,
        duplicates_removed=duplicates,
        skipped={reason: int(n) for reason, n in sorted(skipped.items())},
        text_count=summary["text_count"],
        scored_count=summary["scored_count"],
        counts=summary["counts"],
        coverage=summary["coverage"],
        mean_score=summary["mean_score"],
        label=summary["label"],
        earliest_published=published[0] if published else None,
        latest_published=published[-1] if published else None,
        items=items,
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        raise
    return record


def score_submitted_texts(db: Session, symbol: str, texts: list[str]) -> SentimentResult:
    symbol = normalize_symbol(symbol)
    candidates = [
        {
            "text": text,
            "dedupe_key": sentiment_engine.normalize_for_dedup(text),
            "source": None,
            "published_at": None,
            "url": None,
        }
        for text in texts
    ]
    return _record(
        db,
        symbol=symbol,
        source_type="text",
        provider=None,
        query=None,
        received_count=len(texts),
        candidates=candidates,
        skipped=Counter(),
    )


def fetch_and_score_news(
    db: Session, symbol: str, query: str | None, provider: NewsProvider, page_size: int
) -> SentimentResult:
    symbol = normalize_symbol(symbol)
    query = normalize_query(query, symbol)
    common = dict(symbol=symbol, source_type="news", provider=provider.name, query=query)

    try:
        articles = provider.fetch_headlines(query, page_size)
    except ProviderError as exc:
        logger.error("News provider %s failed for %s: %s", provider.name, symbol, exc.code)
        return _record(
            db, **common, received_count=0, candidates=[], skipped=Counter(),
            error_code=exc.code, error_message=exc.message,
        )
    except Exception as exc:  # noqa: BLE001 — log the type only: messages can embed URLs/keys
        logger.error("Unexpected news failure for %s: %s", symbol, type(exc).__name__)
        return _record(
            db, **common, received_count=0, candidates=[], skipped=Counter(),
            error_code="NEWS_FETCH_FAILURE", error_message="The news request failed unexpectedly.",
        )

    candidates, skipped = _candidates_from_articles(articles)
    return _record(
        db, **common, received_count=len(articles), candidates=candidates, skipped=skipped
    )


def get_latest_result(db: Session, symbol: str, source_type: str | None = None) -> SentimentResult | None:
    symbol = normalize_symbol(symbol)
    query = db.query(SentimentResult).filter(SentimentResult.symbol == symbol)
    if source_type:
        query = query.filter(SentimentResult.source_type == source_type)
    return query.order_by(SentimentResult.created_at.desc()).first()
