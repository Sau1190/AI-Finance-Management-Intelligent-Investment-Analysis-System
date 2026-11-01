"""Collects scoring inputs from the STORED results of earlier phases.

Nothing is fetched, recomputed, repaired, or estimated here: each indicator is
read exactly as an earlier phase stored it. Where an input is absent the reason
is recorded (so the explanation can say why) and the engine excludes it.

Choice rules (all explicit, never silent):
  * Technical / sentiment / risk: the latest COMPLETE result for the symbol.
  * Fundamentals: the latest COMPLETE Phase 5 result for the file you name;
    if the file has several analysed worksheets you must name one; rows are
    matched to the symbol by a `ticker` column (a `company` column is accepted
    only when the sheet holds a single company); the LATEST PERIOD is the row
    with the greatest parseable date (file order if there is no date column).
    If the latest period is ambiguous (several rows share it) or has no value
    for a metric, that input is missing — older periods are never substituted.
"""

import math

import pandas as pd
from sqlalchemy.orm import Session

from app.models.fundamental_analysis_result import FundamentalAnalysisResult
from app.models.risk_analysis_result import RiskAnalysisResult
from app.models.sentiment_result import SentimentResult
from app.services import analysis_storage, fundamental_metrics, scoring_config as cfg, technical_service


def _unavailable(reason: str) -> dict:
    return {"unavailable_reason": reason, "values": {}, "missing": {}, "warnings": [], "source_ref": {}, "as_of": None}


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


# ---------------------------------------------------------------------------
# Technical (Phase 7)
# ---------------------------------------------------------------------------


def gather_technical(db: Session, symbol: str) -> dict:
    result = technical_service.get_latest_result(db, symbol, completed_only=True)
    if result is None:
        return _unavailable(f"No successful technical analysis exists for {symbol}. Run it first.")

    row = result.preview_rows[-1] if result.preview_rows else None
    if row is None or row.get("date") != result.last_date:
        return _unavailable("The stored technical result has no row for its latest bar.")
    reports = {i["key"]: i for i in result.indicators}
    close = _finite(row.get("close"))

    values: dict[str, float | None] = {}
    missing: dict[str, str] = {}
    for key, sma_key in (("price_vs_sma_50", "sma_50"), ("price_vs_sma_200", "sma_200")):
        report = reports.get(sma_key, {})
        sma = _finite(row.get(sma_key))
        if report.get("status") != "COMPUTED":
            missing[key] = report.get("reason") or f"{sma_key} was not computed."
        elif close is None or sma is None or sma <= 0:
            missing[key] = f"No usable close or {sma_key} on the latest bar."
        else:
            values[key] = close / sma - 1.0
    return {
        "unavailable_reason": None,
        "values": values,
        "missing": missing,
        "warnings": [],
        "as_of": result.last_date,
        "source_ref": {
            "kind": "technical", "result_id": result.id, "market_snapshot_id": result.market_snapshot_id,
            "created_at": result.created_at.isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# Sentiment (Phase 8)
# ---------------------------------------------------------------------------


def gather_sentiment(db: Session, symbol: str) -> dict:
    result = (
        db.query(SentimentResult)
        .filter(SentimentResult.symbol == symbol, SentimentResult.status == "COMPLETE")
        .order_by(SentimentResult.created_at.desc())
        .first()
    )
    if result is None:
        return _unavailable(f"No successful sentiment analysis exists for {symbol}. Run it first.")

    values: dict[str, float | None] = {}
    missing: dict[str, str] = {}
    mean = _finite(result.mean_score)
    if result.scored_count < cfg.MIN_SENTIMENT_SCORED_TEXTS:
        missing["sentiment_mean"] = (
            f"Only {result.scored_count} text(s) carried a sentiment signal; "
            f"at least {cfg.MIN_SENTIMENT_SCORED_TEXTS} are needed."
        )
    elif mean is None:
        missing["sentiment_mean"] = "The sentiment result has no mean score."
    else:
        values["sentiment_mean"] = mean

    warnings = []
    if result.coverage is not None and result.coverage < 0.5:
        warnings.append(
            f"Only {result.scored_count} of {result.text_count} texts carried a sentiment signal "
            f"(coverage {result.coverage:.0%})."
        )
    return {
        "unavailable_reason": None,
        "values": values,
        "missing": missing,
        "warnings": warnings,
        "as_of": result.latest_published,
        "source_ref": {
            "kind": "sentiment", "result_id": result.id, "source_type": result.source_type,
            "text_count": result.text_count, "scored_count": result.scored_count,
            "lexicon_version": result.lexicon_version, "created_at": result.created_at.isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# Risk (Phase 9)
# ---------------------------------------------------------------------------


def gather_risk(db: Session, symbol: str) -> dict:
    result = (
        db.query(RiskAnalysisResult)
        .filter(RiskAnalysisResult.symbol == symbol, RiskAnalysisResult.status == "COMPLETE")
        .order_by(RiskAnalysisResult.created_at.desc())
        .first()
    )
    if result is None:
        return _unavailable(f"No successful risk analysis exists for {symbol}. Run it first.")

    reports = {m["key"]: m for m in result.metrics}
    values: dict[str, float | None] = {}
    missing: dict[str, str] = {}
    for key in ("annualized_volatility", "max_drawdown", "historical_var_95"):
        report = reports.get(key, {})
        value = _finite(report.get("value"))
        if report.get("status") == "COMPUTED" and value is not None:
            values[key] = value
        else:
            missing[key] = report.get("reason") or f"{key} was not computed."
    return {
        "unavailable_reason": None,
        "values": values,
        "missing": missing,
        "warnings": list(result.warnings),
        "as_of": result.last_date,
        "source_ref": {
            "kind": "risk", "result_id": result.id, "market_snapshot_id": result.market_snapshot_id,
            "created_at": result.created_at.isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# Fundamentals (Phase 5)
# ---------------------------------------------------------------------------


def _select_sheet(result: FundamentalAnalysisResult, sheet_name: str | None) -> tuple[dict | None, str | None]:
    analysed = [w for w in result.worksheets if w.get("status") == "ANALYZED"]
    if sheet_name is not None:
        for sheet in analysed:
            if sheet.get("sheet_name") == sheet_name:
                return sheet, None
        return None, f"Worksheet '{sheet_name}' was not found among the analysed worksheets of this file."
    if not analysed:
        return None, "No worksheet of this file was analysed successfully."
    if len(analysed) > 1:
        names = ", ".join(f"'{w.get('sheet_name')}'" for w in analysed)
        return None, f"The file has several analysed worksheets ({names}); pass sheet_name to choose one."
    return analysed[0], None


def _select_rows(sheet: dict, rows: list[dict], symbol: str) -> tuple[list[dict] | None, str | None]:
    entity_column = sheet.get("entity_column")
    if entity_column == "ticker":
        chosen = [r for r in rows if (r.get("ticker") or "").strip().upper() == symbol]
        if not chosen:
            return None, f"No rows for ticker {symbol} in this worksheet."
        return chosen, None
    if entity_column == "company":
        names = {(r.get("company") or "").strip() for r in rows} - {""}
        if len(names) != 1:
            return None, (
                "The worksheet identifies entities by company name, which cannot be matched to a ticker "
                "symbol; use a single-company worksheet or add a ticker column."
            )
        only = next(iter(names))
        return [r for r in rows if (r.get("company") or "").strip() == only], None
    return rows, None


def _latest_row(sheet: dict, rows: list[dict]) -> tuple[dict | None, str, str | None]:
    """Return (row, basis, problem). basis is "date" or "file order"."""
    if sheet.get("date_column"):
        parsed = fundamental_metrics.parse_dates(pd.Series([r.get("date") or None for r in rows]))
        dated = [(p, r) for p, r in zip(parsed, rows) if p is not None]
        if not dated:
            return None, "date", "None of the rows has a parseable date, so the latest period cannot be determined."
        newest = max(p for p, _ in dated)
        newest_rows = [r for p, r in dated if p == newest]
        if len(newest_rows) > 1:
            return None, "date", "Several rows share the latest period, so the latest period is ambiguous."
        return newest_rows[0], "date", None
    return max(rows, key=lambda r: int(r.get("row_index") or 0)), "file order", None


def gather_fundamental(db: Session, file_id: str | None, symbol: str, sheet_name: str | None) -> dict:
    if file_id is None:
        return _unavailable("No file_id was given, so fundamentals were not used.")
    result = (
        db.query(FundamentalAnalysisResult)
        .filter(FundamentalAnalysisResult.file_id == file_id, FundamentalAnalysisResult.status == "COMPLETE")
        .order_by(FundamentalAnalysisResult.created_at.desc())
        .first()
    )
    if result is None:
        return _unavailable("No successful fundamental analysis exists for this file. Process and analyse it first.")

    sheet, problem = _select_sheet(result, sheet_name)
    if sheet is None:
        return _unavailable(problem)
    key = sheet.get("metrics_storage_key")
    rows = analysis_storage.read_csv_rows(key) if key else None
    if not rows:
        return _unavailable("The stored fundamental metrics for this worksheet are no longer available.")

    selected, problem = _select_rows(sheet, rows, symbol)
    if selected is None:
        return _unavailable(problem)
    latest, basis, problem = _latest_row(sheet, selected)
    if latest is None:
        return _unavailable(problem)

    reports = {m["key"]: m for m in sheet.get("metrics", [])}
    values: dict[str, float | None] = {}
    missing: dict[str, str] = {}
    for indicator in cfg.COMPONENTS["fundamental"]["indicators"]:
        ikey = indicator["key"]
        value = _finite(latest.get(ikey)) if (latest.get(ikey) or "").strip() != "" else None
        if value is not None:
            values[ikey] = value
        else:
            report = reports.get(ikey, {})
            if report.get("status") == "NOT_COMPUTABLE":
                missing[ikey] = report.get("reason") or "The metric was not computable."
            else:
                missing[ikey] = (
                    "The latest period has no value for this metric (it was skipped for that row; "
                    "see the Phase 5 result for the reasons)."
                )
    return {
        "unavailable_reason": None,
        "values": values,
        "missing": missing,
        "warnings": list(sheet.get("warnings", [])),
        "as_of": (latest.get("date") or None) if basis == "date" else None,
        "source_ref": {
            "kind": "fundamental", "result_id": result.id, "file_id": file_id,
            "sheet_name": sheet.get("sheet_name"), "entity_column": sheet.get("entity_column"),
            "latest_row_index": int(latest.get("row_index") or 0), "latest_row_basis": basis,
            "processing_result_id": result.processing_result_id, "created_at": result.created_at.isoformat(),
        },
    }


def gather_all(db: Session, symbol: str, file_id: str | None, sheet_name: str | None) -> dict[str, dict]:
    return {
        "fundamental": gather_fundamental(db, file_id, symbol, sheet_name),
        "technical": gather_technical(db, symbol),
        "sentiment": gather_sentiment(db, symbol),
        "risk": gather_risk(db, symbol),
    }
