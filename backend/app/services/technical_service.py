"""Orchestrates Phase 7: take a symbol's latest SUCCESSFUL Phase 6 price
snapshot, compute technical indicators with app.services.technical_report,
store the per-bar series, and persist an explainable result.

Rules (consistent with the rest of the project):
  * Only stored, validated bars are used; nothing is fetched here and no price
    is ever invented or filled in.
  * A result records which market snapshot it came from.
  * A run that cannot produce anything (data file gone, too few bars, storage
    failure, unexpected error) is a FAILED result with an error code — not an
    exception, and never a COMPLETE result missing its file.
  * Indicators describe; they never recommend (no buy/sell/overbought labels).
"""

import csv
import io
import logging

from sqlalchemy.orm import Session

from app.core.exceptions import AnalysisRequestError
from app.models.market_data_snapshot import MarketDataSnapshot
from app.models.technical_analysis_result import TechnicalAnalysisResult, TechnicalRunStatus
from app.services import analysis_storage, market_service, market_storage, technical_report

logger = logging.getLogger(__name__)


def _failed(snapshot: MarketDataSnapshot, code: str, message: str, bar_count: int = 0) -> dict:
    return {
        "status": TechnicalRunStatus.FAILED.value,
        "error_code": code,
        "error_message": message,
        "bar_count": bar_count,
        "first_date": None,
        "last_date": None,
        "indicators": [],
        "preview_rows": [],
        "storage_key": None,
    }


def _run(snapshot: MarketDataSnapshot) -> dict:
    """Compute everything for one snapshot; returns the field values for the
    result row. Any artifact written is referenced by `storage_key`.
    """
    bars = market_storage.read_bars_csv(snapshot.bars_storage_key) if snapshot.bars_storage_key else None
    if bars is None:
        return _failed(
            snapshot,
            "MARKET_DATA_UNAVAILABLE",
            "The stored price data for this symbol is no longer available. Fetch it again.",
        )
    if len(bars) < technical_report.MIN_BARS_FOR_ANY:
        return _failed(
            snapshot,
            "INSUFFICIENT_DATA",
            f"No indicator could be computed: {len(bars)} bars available, "
            f"at least {technical_report.MIN_BARS_FOR_ANY} needed.",
            bar_count=len(bars),
        )

    try:
        indicators, preview_rows, csv_text = technical_report.build_report(bars)
    except Exception as exc:  # noqa: BLE001 — log the type only; never leave a half result
        logger.error("Technical analysis failed for %s: %s", snapshot.symbol, type(exc).__name__)
        return _failed(snapshot, "TECHNICAL_ANALYSIS_FAILURE", "The technical analysis failed unexpectedly.")

    storage_key = None
    if csv_text is not None:
        try:
            _, storage_key = analysis_storage.save_metrics_csv(csv_text)
        except AnalysisRequestError:
            logger.error("Storage failure saving technical indicators for %s", snapshot.symbol)
            return _failed(
                snapshot,
                "ANALYSIS_STORAGE_FAILURE",
                "The indicator series could not be saved. Nothing was kept.",
                bar_count=len(bars),
            )

    return {
        "status": TechnicalRunStatus.COMPLETE.value,
        "error_code": None,
        "error_message": None,
        "bar_count": len(bars),
        "first_date": bars[0]["date"],
        "last_date": bars[-1]["date"],
        "indicators": indicators,
        "preview_rows": preview_rows,
        "storage_key": storage_key,
    }


def analyze_technical(db: Session, symbol: str) -> TechnicalAnalysisResult:
    symbol = market_service.normalize_symbol(symbol)
    snapshot = market_service.get_latest_snapshot(db, symbol, completed_only=True)
    if snapshot is None:
        raise AnalysisRequestError(
            "MARKET_DATA_NOT_FOUND",
            "No market data has been fetched for this symbol yet. Fetch it first, then run the analysis.",
            status_code=404,
        )

    fields = _run(snapshot)
    record = TechnicalAnalysisResult(
        symbol=symbol,
        market_snapshot_id=snapshot.id,
        status=fields["status"],
        error_code=fields["error_code"],
        error_message=fields["error_message"],
        bar_count=fields["bar_count"],
        first_date=fields["first_date"],
        last_date=fields["last_date"],
        indicators=fields["indicators"],
        preview_rows=fields["preview_rows"],
        indicators_storage_key=fields["storage_key"],
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        if fields["storage_key"]:
            analysis_storage.delete_artifacts([fields["storage_key"]])
        raise
    return record


def get_latest_result(
    db: Session, symbol: str, *, completed_only: bool = False
) -> TechnicalAnalysisResult | None:
    symbol = market_service.normalize_symbol(symbol)
    query = db.query(TechnicalAnalysisResult).filter(TechnicalAnalysisResult.symbol == symbol)
    if completed_only:
        query = query.filter(TechnicalAnalysisResult.status == TechnicalRunStatus.COMPLETE.value)
    return query.order_by(TechnicalAnalysisResult.created_at.desc()).first()


def read_series(db: Session, symbol: str, limit: int) -> tuple[TechnicalAnalysisResult, int, list[dict]]:
    """Most recent `limit` rows (ascending by date) of the latest COMPLETE
    result. Returns (result, total_rows, rows).
    """
    result = get_latest_result(db, symbol, completed_only=True)
    if result is None or not result.indicators_storage_key:
        raise AnalysisRequestError(
            "TECHNICAL_SERIES_NOT_FOUND",
            "No successful technical analysis exists for this symbol yet.",
            status_code=404,
        )
    raw_rows = analysis_storage.read_csv_rows(result.indicators_storage_key)
    if raw_rows is None:
        raise AnalysisRequestError(
            "TECHNICAL_DATA_UNAVAILABLE",
            "The stored indicator series is no longer available. Run the analysis again.",
            status_code=404,
        )
    try:
        rows = [
            {column: (value if column == "date" else (float(value) if value != "" else None))
             for column, value in row.items()}
            for row in raw_rows
        ]
    except ValueError:
        raise AnalysisRequestError(
            "TECHNICAL_DATA_UNAVAILABLE",
            "The stored indicator series is no longer available. Run the analysis again.",
            status_code=404,
        ) from None
    return result, len(rows), rows[-limit:]
