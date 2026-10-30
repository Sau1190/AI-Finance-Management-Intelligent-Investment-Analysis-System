"""Header detection and data-quality checks.

Beginner view:
  Before we can trust a spreadsheet's columns, we need to know which row is
  actually the header (it isn't always row 1), what type of data each column
  holds, and where the data is messy (missing, duplicated, inconsistent).

Technical view:
  All heuristics here are deterministic and explainable — scored rules over
  a pandas DataFrame, no ML, no LLM. Every function documents exactly what
  it measures so results are reproducible and auditable.
"""

import re

import pandas as pd

MAX_HEADER_SCAN_ROWS = 10
HEADER_SCORE_THRESHOLD = 0.5
INCONSISTENCY_MIN_TYPE_RATIO = 0.9
MAX_INCONSISTENCY_EXAMPLES = 3
MAX_EXAMPLE_LENGTH = 50

_NUMERIC_CLEAN_RE = re.compile(r"[,$%\s]")
_BOOLEAN_VALUES = {"true", "false", "yes", "no", "y", "n"}


def _looks_numeric(value: str) -> bool:
    cleaned = _NUMERIC_CLEAN_RE.sub("", value)
    if not cleaned:
        return False
    try:
        float(cleaned)
        return True
    except ValueError:
        return False


def _row_signature(row: pd.Series) -> dict:
    """Score one raw row as a header candidate. Returns the components used
    so the decision is auditable, not just a single opaque number.
    """
    non_null = row.dropna()
    non_null = non_null[non_null.astype(str).str.strip() != ""]
    total = len(row)
    if total == 0 or non_null.empty:
        return {"non_null_ratio": 0.0, "string_ratio": 0.0, "uniqueness_ratio": 0.0, "numeric_ratio": 0.0}

    values = non_null.astype(str).str.strip()
    non_null_ratio = len(non_null) / total
    numeric_flags = values.map(_looks_numeric)
    numeric_ratio = numeric_flags.mean()
    string_ratio = 1.0 - numeric_ratio
    uniqueness_ratio = values.nunique() / len(values)
    return {
        "non_null_ratio": non_null_ratio,
        "string_ratio": string_ratio,
        "uniqueness_ratio": uniqueness_ratio,
        "numeric_ratio": numeric_ratio,
    }


def detect_header_row(raw: pd.DataFrame) -> tuple[int, bool]:
    """Scan the first rows of a header-less DataFrame and pick the most
    likely header row.

    Score = 0.4 * string_ratio + 0.3 * uniqueness_ratio + 0.3 * non_null_ratio,
    with a bonus if the following row is meaningfully more numeric than the
    candidate row (a common header -> data transition).

    Returns (header_row_index, assumed_default). `assumed_default` is True
    when no candidate scored above the threshold and we fell back to row 0 —
    callers should surface this as a warning, not silently trust it.
    """
    scan_limit = min(MAX_HEADER_SCAN_ROWS, len(raw))
    best_index = 0
    best_score = -1.0
    for i in range(scan_limit):
        signature = _row_signature(raw.iloc[i])
        score = 0.4 * signature["string_ratio"] + 0.3 * signature["uniqueness_ratio"] + 0.3 * signature["non_null_ratio"]
        if i + 1 < len(raw):
            next_signature = _row_signature(raw.iloc[i + 1])
            if next_signature["numeric_ratio"] - signature["numeric_ratio"] >= 0.3:
                score += 0.15
        if score > best_score:
            best_score = score
            best_index = i

    # best_score accumulates numpy.float64 from pandas .mean() calls, so the
    # comparison below is numpy.bool_, not a JSON-serializable Python bool.
    assumed_default = bool(best_score < HEADER_SCORE_THRESHOLD)
    return best_index, assumed_default


def infer_column_type(series: pd.Series) -> str:
    """Classify a column as one of: date, integer, float, boolean, string,
    unknown (entirely empty). Classification requires >= 90% of non-null
    values to conform — a handful of stray values do not change the type,
    they become inconsistent-value findings instead.
    """
    non_null = series.dropna()
    non_null = non_null[non_null.astype(str).str.strip() != ""]
    if non_null.empty:
        return "unknown"

    values = non_null.astype(str).str.strip()

    lowered = values.str.lower()
    if lowered.isin(_BOOLEAN_VALUES).mean() >= INCONSISTENCY_MIN_TYPE_RATIO:
        return "boolean"

    # Bare numeric strings ("1000", "1000.50") are financial figures, not
    # dates — pandas.to_datetime will happily parse "1000" as a date (e.g.
    # a bare year), which is almost never the intent for a revenue/price
    # column. Only attempt date detection when the column is not already
    # overwhelmingly numeric-looking, so numeric columns can't be hijacked.
    numeric_ratio = values.map(_looks_numeric).mean()
    if numeric_ratio < INCONSISTENCY_MIN_TYPE_RATIO:
        parsed_dates = pd.to_datetime(non_null, errors="coerce", format="mixed")
        if parsed_dates.notna().mean() >= INCONSISTENCY_MIN_TYPE_RATIO:
            return "date"

    cleaned = values.str.replace(_NUMERIC_CLEAN_RE, "", regex=True)
    numeric = pd.to_numeric(cleaned, errors="coerce")
    if numeric.notna().mean() >= INCONSISTENCY_MIN_TYPE_RATIO:
        finite = numeric.dropna()
        if not finite.empty and (finite % 1 == 0).all():
            return "integer"
        return "float"

    return "string"


def count_missing_values(series: pd.Series) -> int:
    """Null plus blank/whitespace-only strings — both mean "no value"."""
    non_null = series.dropna()
    blank = non_null.astype(str).str.strip().eq("").sum()
    return int(series.isna().sum() + blank)


def find_inconsistent_values(series: pd.Series, column_type: str) -> dict | None:
    """For a typed column (date/integer/float/boolean), find non-null values
    that do not conform to that type. Returns None when the column is
    "string"/"unknown" (everything conforms by definition) or nothing is
    inconsistent.
    """
    if column_type in {"string", "unknown"}:
        return None

    non_null = series.dropna()
    non_null = non_null[non_null.astype(str).str.strip() != ""]
    if non_null.empty:
        return None

    values = non_null.astype(str).str.strip()
    if column_type == "boolean":
        conforms = values.str.lower().isin(_BOOLEAN_VALUES)
    elif column_type == "date":
        conforms = pd.to_datetime(non_null, errors="coerce", format="mixed").notna()
    else:  # integer / float
        cleaned = values.str.replace(_NUMERIC_CLEAN_RE, "", regex=True)
        conforms = pd.to_numeric(cleaned, errors="coerce").notna()

    bad_values = values[~conforms]
    if bad_values.empty:
        return None

    examples = [v[:MAX_EXAMPLE_LENGTH] for v in bad_values.head(MAX_INCONSISTENCY_EXAMPLES).tolist()]
    return {"count": int(len(bad_values)), "examples": examples}


def count_duplicate_rows(df: pd.DataFrame) -> int:
    """Rows identical to an earlier row (the first occurrence is not counted)."""
    if df.empty:
        return 0
    return int(df.duplicated(keep="first").sum())
