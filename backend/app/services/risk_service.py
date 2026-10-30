"""Orchestrates Phase 9: take a symbol's latest SUCCESSFUL Phase 6 price
snapshot (and a benchmark's, if asked), compute market-risk metrics with
app.services.risk_report, and persist an explainable result.

Rules (consistent with the rest of the project):
  * Only stored, validated bars are used; nothing is fetched here and no price
    is invented, adjusted, or filled in.
  * A result records which snapshot(s) it used.
  * A run that cannot produce anything (data file gone, too few bars,
    unexpected error) is a FAILED result with an error code, not an exception.
  * Metrics describe the past; they never label anything high/low risk.
"""

import logging

from sqlalchemy.orm import Session

from app.core.exceptions import AnalysisRequestError
from app.models.market_data_snapshot import MarketDataSnapshot
from app.models.risk_analysis_result import RiskAnalysisResult, RiskRunStatus
from app.services import market_service, market_storage, risk_report

logger = logging.getLogger(__name__)

MIN_BARS = 2


def _latest_bars(db: Session, symbol: str, missing_code: str) -> tuple[MarketDataSnapshot, list[dict] | None]:
    snapshot = market_service.get_latest_snapshot(db, symbol, completed_only=True)
    if snapshot is None:
        raise AnalysisRequestError(
            missing_code,
            f"No market data has been fetched for {symbol} yet. Fetch it first, then run the analysis.",
            status_code=404,
        )
    bars = market_storage.read_bars_csv(snapshot.bars_storage_key) if snapshot.bars_storage_key else None
    return snapshot, bars


def _failed(code: str, message: str, bar_count: int = 0) -> dict:
    return {
        "status": RiskRunStatus.FAILED.value, "error_code": code, "error_message": message,
        "bar_count": bar_count, "returns_count": 0, "first_date": None, "last_date": None,
        "metrics": [], "warnings": [],
    }


def _run(symbol: str, bars, benchmark_symbol: str | None, benchmark_bars) -> dict:
    if bars is None or (benchmark_symbol is not None and benchmark_bars is None):
        return _failed(
            "MARKET_DATA_UNAVAILABLE",
            "Stored price data for this analysis is no longer available. Fetch it again.",
        )
    if len(bars) < MIN_BARS:
        return _failed(
            "INSUFFICIENT_DATA",
            f"No risk metric could be computed: {len(bars)} bar(s) available, at least {MIN_BARS} needed.",
            bar_count=len(bars),
        )
    try:
        metrics, warnings, returns_count = risk_report.build_report(
            symbol, bars, benchmark_symbol, benchmark_bars
        )
    except Exception as exc:  # noqa: BLE001 — log the type only; never leave a half result
        logger.error("Risk analysis failed for %s: %s", symbol, type(exc).__name__)
        return _failed("RISK_ANALYSIS_FAILURE", "The risk analysis failed unexpectedly.")
    return {
        "status": RiskRunStatus.COMPLETE.value, "error_code": None, "error_message": None,
        "bar_count": len(bars), "returns_count": returns_count,
        "first_date": bars[0]["date"], "last_date": bars[-1]["date"],
        "metrics": metrics, "warnings": warnings,
    }


def analyze_risk(db: Session, symbol: str, benchmark: str | None = None) -> RiskAnalysisResult:
    symbol = market_service.normalize_symbol(symbol)
    benchmark_symbol = market_service.normalize_symbol(benchmark) if benchmark is not None else None
    if benchmark_symbol == symbol:
        raise AnalysisRequestError(
            "INVALID_BENCHMARK", "The benchmark must be a different symbol from the one analysed.", status_code=400
        )

    snapshot, bars = _latest_bars(db, symbol, "MARKET_DATA_NOT_FOUND")
    benchmark_snapshot = benchmark_bars = None
    if benchmark_symbol is not None:
        benchmark_snapshot, benchmark_bars = _latest_bars(db, benchmark_symbol, "BENCHMARK_DATA_NOT_FOUND")

    fields = _run(symbol, bars, benchmark_symbol, benchmark_bars)
    record = RiskAnalysisResult(
        symbol=symbol,
        benchmark_symbol=benchmark_symbol,
        market_snapshot_id=snapshot.id,
        benchmark_snapshot_id=benchmark_snapshot.id if benchmark_snapshot else None,
        **fields,
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        raise
    return record


def get_latest_result(db: Session, symbol: str) -> RiskAnalysisResult | None:
    symbol = market_service.normalize_symbol(symbol)
    return (
        db.query(RiskAnalysisResult)
        .filter(RiskAnalysisResult.symbol == symbol)
        .order_by(RiskAnalysisResult.created_at.desc())
        .first()
    )
