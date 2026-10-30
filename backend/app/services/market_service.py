"""Orchestrates Phase 6: ask a provider for daily prices, validate them,
store the accepted bars, and record an explainable snapshot.

Rules (consistent with the rest of the project):
  * Never fabricate or repair data. Bars are accepted as received or rejected
    with a counted reason; if nothing valid remains the fetch is FAILED.
  * A provider problem (rate limit, unknown symbol, timeout...) is a normal
    FAILED snapshot, not a server error.
  * A snapshot is COMPLETE only if its stored file exists. Storage failure
    fails the fetch; if the database row cannot be saved the file is removed.
  * Messages shown to users are authored here/in the adapter — never raw
    provider text, URLs, or exception strings (the URL carries the API key).
"""

import logging
import re
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import MarketDataRequestError
from app.models.market_data_snapshot import FetchStatus, MarketDataSnapshot
from app.services import market_storage, market_validation
from app.services.market_providers import MarketDataProvider, ProviderError

logger = logging.getLogger(__name__)

PREVIEW_BARS = 5
_SYMBOL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,9}$")


def normalize_symbol(symbol: str) -> str:
    """Upper-case a ticker after strict validation. Rejecting everything else
    keeps odd input (paths, spaces, query fragments) out of provider requests
    and storage.
    """
    if not isinstance(symbol, str) or not _SYMBOL.match(symbol):
        raise MarketDataRequestError(
            "INVALID_SYMBOL",
            "A symbol must be 1-10 characters: letters, digits, '.' or '-'.",
            status_code=400,
        )
    return symbol.upper()


def fetch_and_store(
    db: Session,
    symbol: str,
    history: str,
    provider: MarketDataProvider,
    *,
    today: date | None = None,
) -> MarketDataSnapshot:
    symbol = normalize_symbol(symbol)
    today = today or datetime.now(timezone.utc).date()

    error_code: str | None = None
    error_message: str | None = None
    bars: list[dict] = []
    rejected: dict[str, int] = {}

    try:
        raw_bars = provider.fetch_daily(symbol, history)
    except ProviderError as exc:
        logger.error("Market data provider %s failed for %s: %s", provider.name, symbol, exc.code)
        error_code, error_message = exc.code, exc.message
    except Exception as exc:  # noqa: BLE001 — log the type only: messages can embed URLs/keys
        logger.error("Unexpected market data failure for %s: %s", symbol, type(exc).__name__)
        error_code, error_message = "MARKET_DATA_FAILURE", "The market data request failed unexpectedly."
    else:
        if not raw_bars:
            error_code, error_message = "PROVIDER_NO_DATA", "The provider returned no price data for this symbol."
        else:
            bars, counts = market_validation.validate_bars(raw_bars, today)
            rejected = {reason: int(n) for reason, n in sorted(counts.items())}
            if not bars:
                error_code = "NO_VALID_BARS"
                error_message = (
                    f"All {len(raw_bars)} bars returned by the provider failed validation; none were stored."
                )

    storage_key: str | None = None
    if error_code is None:
        try:
            _, storage_key = market_storage.save_bars_csv(market_storage.bars_to_csv(bars))
        except MarketDataRequestError:
            logger.error("Storage failure saving market data for %s", symbol)
            error_code = "MARKET_STORAGE_FAILURE"
            error_message = "The price data could not be saved. Nothing was kept."

    complete = error_code is None
    record = MarketDataSnapshot(
        symbol=symbol,
        provider=provider.name,
        history=history,
        status=(FetchStatus.COMPLETE if complete else FetchStatus.FAILED).value,
        error_code=error_code,
        error_message=error_message,
        bar_count=len(bars) if complete else 0,
        first_date=bars[0]["date"] if complete else None,
        last_date=bars[-1]["date"] if complete else None,
        rejected_bars=rejected,
        preview_bars=bars[-PREVIEW_BARS:] if complete else [],
        bars_storage_key=storage_key,
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        if storage_key:
            market_storage.delete_artifacts([storage_key])
        raise
    return record


def get_latest_snapshot(db: Session, symbol: str, *, completed_only: bool = False) -> MarketDataSnapshot | None:
    symbol = normalize_symbol(symbol)
    query = db.query(MarketDataSnapshot).filter(MarketDataSnapshot.symbol == symbol)
    if completed_only:
        query = query.filter(MarketDataSnapshot.status == FetchStatus.COMPLETE.value)
    return query.order_by(MarketDataSnapshot.created_at.desc()).first()


def read_prices(db: Session, symbol: str, limit: int) -> tuple[MarketDataSnapshot, list[dict]]:
    """Most recent `limit` bars (ascending) from the latest COMPLETE snapshot."""
    snapshot = get_latest_snapshot(db, symbol, completed_only=True)
    if snapshot is None or not snapshot.bars_storage_key:
        raise MarketDataRequestError(
            "PRICES_NOT_FOUND",
            "No successful market data fetch exists for this symbol yet.",
            status_code=404,
        )
    bars = market_storage.read_bars_csv(snapshot.bars_storage_key)
    if bars is None:
        raise MarketDataRequestError(
            "MARKET_DATA_UNAVAILABLE",
            "The stored price data for this symbol is no longer available. Fetch it again.",
            status_code=404,
        )
    return snapshot, bars[-limit:]
