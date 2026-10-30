"""Deterministic fundamental metrics from Phase 2's cleaned, normalized data.

Beginner view:
  Given a table with columns like revenue, net_income, assets and equity,
  this works out standard ratios (e.g. net profit margin = net income /
  revenue) and period-over-period growth. It says WHAT the numbers are and
  exactly HOW each was computed. It never says whether a number is good or
  bad — that judgement belongs to the later scoring phase.

Technical view:
  Pure functions over a DataFrame of strings (a cleaned CSV read back with
  dtype=str). No database, no storage, no network, no LLM. Rules that keep it
  honest and explainable:
    * A ratio is computed only when both inputs parse as finite numbers AND
      the denominator is > 0. Anything else is SKIPPED with a counted,
      human-readable reason — never a guessed, defaulted, or sign-flipped value.
    * Concepts are never substituted for each other (`sales` is not assumed to
      be `revenue`, `profit` is not assumed to be `net_income`). A metric whose
      input column is absent or ambiguous is NOT_COMPUTABLE, and says why.
    * Rows are never de-duplicated or silently reordered. Growth is ordered by
      date within each ticker/company; rows sharing a period are skipped and
      reported, not merged.
    * All values are native Python floats/strs (numpy scalars break JSON storage).
"""

import csv
import io
import math
import statistics
from collections import Counter
from dataclasses import dataclass

import pandas as pd

from app.services.data_quality import _NUMERIC_CLEAN_RE
from app.services.financial_normalization import CANONICAL_COLUMN_VARIANTS

PREVIEW_ROWS = 5

# Concepts that are "the same thing under another name" often enough that a
# reader might expect them to be interchangeable. We do NOT treat them as
# equivalent; we only mention it when explaining why a metric is unavailable.
_NOT_ASSUMED_EQUIVALENT = {
    "revenue": "sales",
    "sales": "revenue",
    "net_income": "profit",
    "profit": "net_income",
}


@dataclass(frozen=True)
class RatioMetric:
    key: str
    label: str
    numerator: str
    denominator: str

    @property
    def formula(self) -> str:
        return f"{self.numerator} / {self.denominator}"

    @property
    def inputs(self) -> list[str]:
        return [self.numerator, self.denominator]


@dataclass(frozen=True)
class GrowthMetric:
    key: str
    label: str
    concept: str

    @property
    def formula(self) -> str:
        return f"({self.concept} - prior {self.concept}) / prior {self.concept}"

    @property
    def inputs(self) -> list[str]:
        return [self.concept, "date"]


RATIO_METRICS: tuple[RatioMetric, ...] = (
    RatioMetric("net_profit_margin", "Net profit margin", "net_income", "revenue"),
    RatioMetric("profit_margin", "Profit margin", "profit", "revenue"),
    RatioMetric("expense_ratio", "Expense ratio", "expenses", "revenue"),
    RatioMetric("return_on_assets", "Return on assets", "net_income", "assets"),
    RatioMetric("return_on_equity", "Return on equity", "net_income", "equity"),
    RatioMetric("debt_to_equity", "Debt to equity", "debt", "equity"),
    RatioMetric("liabilities_to_assets", "Liabilities to assets", "liabilities", "assets"),
    RatioMetric("equity_ratio", "Equity ratio", "equity", "assets"),
    RatioMetric("price_to_earnings", "Price to earnings", "price", "eps"),
)

GROWTH_METRICS: tuple[GrowthMetric, ...] = (
    GrowthMetric("revenue_growth", "Revenue growth (period over period)", "revenue"),
    GrowthMetric("net_income_growth", "Net income growth (period over period)", "net_income"),
)

ANALYSIS_CONCEPTS: frozenset[str] = frozenset(
    {c for m in RATIO_METRICS for c in m.inputs} | {m.concept for m in GROWTH_METRICS}
)

# Parsed column: (values, states). states[i] is "ok", "missing" or "non-numeric".
ParsedColumn = tuple[list[float | None], list[str]]


def parse_numeric_column(series: pd.Series) -> ParsedColumn:
    """Parse strings to floats using the same cleaning Phase 2 uses to decide
    a column is numeric (strip `,`, `$`, `%`, whitespace). A blank is
    "missing"; anything else that is not a finite number is "non-numeric"
    (e.g. accounting-style "(1,200)" is NOT guessed to mean -1200).
    """
    values: list[float | None] = []
    states: list[str] = []
    for raw in series.tolist():
        if pd.isna(raw) or str(raw).strip() == "":
            values.append(None)
            states.append("missing")
            continue
        cleaned = _NUMERIC_CLEAN_RE.sub("", str(raw))
        try:
            number = float(cleaned) if "_" not in cleaned else math.nan
        except ValueError:
            number = math.nan
        if not math.isfinite(number):
            values.append(None)
            states.append("non-numeric")
        else:
            values.append(number)
            states.append("ok")
    return values, states


def compute_ratio(
    metric: RatioMetric, columns: dict[str, ParsedColumn]
) -> tuple[list[float | None], Counter]:
    """Row-wise numerator / denominator. Returns (values, skipped_reasons)."""
    num_values, num_states = columns[metric.numerator]
    den_values, den_states = columns[metric.denominator]
    results: list[float | None] = []
    reasons: Counter = Counter()
    for i in range(len(num_values)):
        reason = None
        if num_states[i] != "ok":
            reason = f"{num_states[i]} {metric.numerator}"
        elif den_states[i] != "ok":
            reason = f"{den_states[i]} {metric.denominator}"
        elif den_values[i] <= 0:  # type: ignore[operator]
            reason = f"non-positive {metric.denominator}"
        if reason is None:
            results.append(num_values[i] / den_values[i])  # type: ignore[operator]
        else:
            results.append(None)
            reasons[reason] += 1
    return results, reasons


def parse_dates(series: pd.Series) -> list[pd.Timestamp | None]:
    """Parse dates deterministically (month-first for ambiguous numeric
    formats, as pandas does; everything normalized to UTC so mixed offsets
    still compare). Unparseable or blank -> None.
    """
    parsed = pd.to_datetime(series, errors="coerce", format="mixed", utc=True)
    return [None if pd.isna(t) else t for t in parsed.tolist()]


def compute_growth(
    metric: GrowthMetric,
    column: ParsedColumn,
    dates: list[pd.Timestamp | None],
    entities: list[str | None] | None,
) -> tuple[list[float | None], Counter, int]:
    """Period-over-period growth: (current - prior) / prior, where "prior" is
    the previous period for the same entity ordered by date (not file order).
    Returns (values, skipped_reasons, rows_in_duplicate_periods).
    """
    values, states = column
    n = len(values)
    results: list[float | None] = [None] * n
    reasons: Counter = Counter()
    duplicate_rows = 0

    groups: dict[str, list[int]] = {}
    for i in range(n):
        if entities is not None:
            entity = entities[i]
            if entity is None:
                reasons["missing entity"] += 1
                continue
            groups.setdefault(entity, []).append(i)
        else:
            groups.setdefault("", []).append(i)

    for indexes in groups.values():
        dated = []
        for i in indexes:
            if dates[i] is None:
                reasons["invalid date"] += 1
            else:
                dated.append(i)
        period_counts = Counter(dates[i] for i in dated)
        unique = [i for i in dated if period_counts[dates[i]] == 1]
        duplicated = len(dated) - len(unique)
        duplicate_rows += duplicated
        if duplicated:
            reasons["duplicate period"] += duplicated
        unique.sort(key=lambda i: (dates[i], i))

        previous: int | None = None
        for i in unique:
            if previous is None:
                reasons["no prior period"] += 1
            elif states[i] != "ok":
                reasons[f"{states[i]} {metric.concept}"] += 1
            elif states[previous] != "ok":
                reasons[f"unusable prior {metric.concept}"] += 1
            elif values[previous] <= 0:  # type: ignore[operator]
                reasons[f"non-positive prior {metric.concept}"] += 1
            else:
                results[i] = (values[i] - values[previous]) / values[previous]  # type: ignore[operator]
            previous = i
    return results, reasons, duplicate_rows


def _unavailable_reason(missing: list[str], df_columns: set[str], ambiguous: list[dict]) -> str:
    """Explain why a metric's inputs are unavailable, without guessing."""
    ambiguous_by_concept = {a["canonical_concept"]: a["source_columns"] for a in ambiguous}
    parts = []
    for concept in missing:
        if concept in ambiguous_by_concept:
            sources = ambiguous_by_concept[concept]
            parts.append(
                f"{concept} is ambiguous ({len(sources)} source columns map to it: {', '.join(sources)})"
            )
            continue
        part = f"{concept} column not found"
        hint = _NOT_ASSUMED_EQUIVALENT.get(concept)
        if hint and hint in df_columns:
            part += f" (a '{hint}' column exists but is not assumed to be equivalent)"
        parts.append(part)
    return "; ".join(parts)


def _summary(values: list[float | None]) -> dict:
    computed = [v for v in values if v is not None]
    if not computed:
        return {"computed_count": 0, "min": None, "max": None, "mean": None}
    return {
        "computed_count": len(computed),
        "min": float(min(computed)),
        "max": float(max(computed)),
        "mean": float(statistics.fmean(computed)),
    }


def _metric_report(metric, status: str, reason: str | None, values=None, reasons=None) -> dict:
    report = {
        "key": metric.key,
        "label": metric.label,
        "formula": metric.formula,
        "inputs": metric.inputs,
        "status": status,
        "reason": reason,
        "computed_count": 0,
        "skipped_count": 0,
        "skipped_reasons": {},
        "min": None,
        "max": None,
        "mean": None,
    }
    if values is not None:
        report.update(_summary(values))
        report["skipped_count"] = int(sum(reasons.values()))
        report["skipped_reasons"] = {k: int(v) for k, v in sorted(reasons.items())}
    return report


def _build_csv(header: list[str], rows: list[list]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if cell is None else cell for cell in row])
    return buffer.getvalue()


def _entity_column(df: pd.DataFrame) -> str | None:
    for candidate in ("ticker", "company"):
        if candidate in df.columns:
            return candidate
    return None


def analyze_sheet(df: pd.DataFrame, ambiguous: list[dict]) -> tuple[dict, str | None]:
    """Analyze one worksheet's cleaned data.

    Returns (sheet_report, metrics_csv_text). `metrics_csv_text` is None when
    no metric could be computed (nothing worth storing). The report never
    contains a storage key — the service adds that after saving.
    """
    columns = set(df.columns)
    recognized = [c for c in CANONICAL_COLUMN_VARIANTS if c in columns]
    report: dict = {
        "sheet_name": "",
        "status": "SKIPPED",
        "reason": None,
        "row_count": int(len(df)),
        "recognized_concepts": recognized,
        "entity_column": None,
        "date_column": "date" if "date" in columns else None,
        "metrics": [],
        "warnings": [],
        "preview_rows": [],
    }

    if len(df) == 0:
        report["reason"] = "The cleaned data has no rows."
        return report, None
    if not (set(recognized) & ANALYSIS_CONCEPTS):
        report["reason"] = (
            "No recognized financial columns were found, so there is nothing to compute"
            + (f" (recognized: {', '.join(recognized)})." if recognized else ".")
        )
        return report, None

    parsed: dict[str, ParsedColumn] = {
        concept: parse_numeric_column(df[concept])
        for concept in ANALYSIS_CONCEPTS
        if concept in columns
    }
    entity_col = _entity_column(df)
    report["entity_column"] = entity_col
    entities: list[str | None] | None = None
    if entity_col is not None:
        entities = [
            None if (pd.isna(v) or str(v).strip() == "") else str(v).strip()
            for v in df[entity_col].tolist()
        ]
    dates = parse_dates(df["date"]) if "date" in columns else None

    computed_series: dict[str, list[float | None]] = {}
    for ratio in RATIO_METRICS:
        missing = [c for c in ratio.inputs if c not in parsed]
        if missing:
            report["metrics"].append(
                _metric_report(ratio, "NOT_COMPUTABLE", _unavailable_reason(missing, columns, ambiguous))
            )
            continue
        values, reasons = compute_ratio(ratio, parsed)
        computed_series[ratio.key] = values
        report["metrics"].append(_metric_report(ratio, "COMPUTED", None, values, reasons))

    for growth in GROWTH_METRICS:
        missing = [c for c in growth.inputs if c not in parsed and c != "date"]
        if dates is None:
            missing.append("date")
        if missing:
            report["metrics"].append(
                _metric_report(growth, "NOT_COMPUTABLE", _unavailable_reason(missing, columns, ambiguous))
            )
            continue
        values, reasons, duplicate_rows = compute_growth(growth, parsed[growth.concept], dates, entities)
        computed_series[growth.key] = values
        report["metrics"].append(_metric_report(growth, "COMPUTED", None, values, reasons))
        if duplicate_rows:
            warning = (
                f"{duplicate_rows} row(s) share the same period for the same "
                f"{entity_col or 'series'}; growth was not computed for them (rows are never merged or dropped)."
            )
            if warning not in report["warnings"]:
                report["warnings"].append(warning)

    if not computed_series:
        report["reason"] = "No metric could be computed from this worksheet's columns; see each metric's reason."
        return report, None

    report["status"] = "ANALYZED"
    header = ["row_index"]
    if entity_col:
        header.append(entity_col)
    if dates is not None:
        header.append("date")
    header.extend(computed_series)

    rows: list[list] = []
    for i in range(len(df)):
        row: list = [i]
        if entity_col:
            row.append(entities[i] if entities is not None else None)
        if dates is not None:
            raw_date = df["date"].iloc[i]
            row.append(None if pd.isna(raw_date) else str(raw_date))
        row.extend(series[i] for series in computed_series.values())
        rows.append(row)

    report["preview_rows"] = [dict(zip(header, row)) for row in rows[:PREVIEW_ROWS]]
    return report, _build_csv(header, rows)
