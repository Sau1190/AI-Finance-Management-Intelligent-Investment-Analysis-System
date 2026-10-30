"""Phase 6 market data API. Thin routes — fetching, validation, and storage
live in app.services.market_service.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import AppError, MarketDataRequestError
from app.schemas.market_data import MarketDataSnapshotResponse, PricesResponse
from app.services import market_service
from app.services.market_providers import MarketDataProvider, ProviderError, build_provider

router = APIRouter(prefix="/market-data", tags=["market-data"])


def _raise_http(exc: AppError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


def get_market_provider() -> MarketDataProvider:
    """Dependency: the configured provider. 503 (nothing recorded) if no
    provider/key is configured — a server setup problem, not a fetch outcome.
    Tests replace this with a fake via app.dependency_overrides.
    """
    settings = get_settings()
    try:
        return build_provider(
            settings.market_data_provider,
            settings.alpha_vantage_api_key,
            settings.market_data_timeout_seconds,
        )
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": exc.message}) from None


@router.post("/{symbol}", response_model=MarketDataSnapshotResponse, status_code=201)
def fetch_market_data(
    symbol: str,
    history: Literal["compact", "full"] = Query("compact"),
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_market_provider),
) -> MarketDataSnapshotResponse:
    """Fetch daily prices for a symbol from the configured provider and store
    them. A fetch the provider cannot satisfy (rate limit, unknown symbol,
    timeout, no valid data) still returns 201 with status=FAILED and an error
    code — an inspectable outcome, not a server error. 400 for an invalid symbol.
    """
    try:
        snapshot = market_service.fetch_and_store(db, symbol, history, provider)
    except MarketDataRequestError as exc:
        _raise_http(exc)
    return MarketDataSnapshotResponse.model_validate(snapshot)


@router.get("/{symbol}", response_model=MarketDataSnapshotResponse)
def get_market_snapshot(symbol: str, db: Session = Depends(get_db)) -> MarketDataSnapshotResponse:
    """The most recent fetch attempt for a symbol (successful or not)."""
    try:
        snapshot = market_service.get_latest_snapshot(db, symbol)
    except MarketDataRequestError as exc:
        _raise_http(exc)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "MARKET_RESULT_NOT_FOUND", "message": "No market data has been fetched for this symbol yet."},
        )
    return MarketDataSnapshotResponse.model_validate(snapshot)


@router.get("/{symbol}/prices", response_model=PricesResponse)
def get_prices(
    symbol: str,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> PricesResponse:
    """The most recent `limit` daily bars (ascending by date) from the latest
    successful fetch.
    """
    try:
        snapshot, bars = market_service.read_prices(db, symbol, limit)
    except MarketDataRequestError as exc:
        _raise_http(exc)
    return PricesResponse(
        symbol=snapshot.symbol,
        snapshot_id=snapshot.id,
        provider=snapshot.provider,
        fetched_at=snapshot.created_at,
        total_bars=snapshot.bar_count,
        returned_bars=len(bars),
        bars=bars,
    )
