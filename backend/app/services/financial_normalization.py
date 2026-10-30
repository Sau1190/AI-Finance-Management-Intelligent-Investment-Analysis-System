"""Deterministic mapping from source column names to canonical financial
concepts.

Beginner view:
  Different spreadsheets name the same thing differently — "Net Sales" and
  "Revenue" often mean the same concept. This module maps known variants to
  one canonical name so later phases can rely on consistent column names.

Technical view:
  Exact-match lookup only, after normalizing a column name (lowercase,
  non-alphanumeric -> underscore, collapse repeats). No fuzzy matching, no
  guessing, no LLM — a name either matches a known variant or it doesn't.
  If two source columns in the same dataset would map to the same canonical
  concept, that is flagged as an ambiguous mapping and NEITHER is renamed —
  we do not silently choose one over the other.
"""

import re

# Canonical concept -> known source-column name variants (already normalized
# to lowercase_with_underscores; the matching function normalizes incoming
# names the same way before comparing).
CANONICAL_COLUMN_VARIANTS: dict[str, set[str]] = {
    "date": {"date", "transaction_date", "period", "reporting_date", "report_date", "fiscal_date"},
    "company": {"company", "company_name", "organization", "entity", "issuer"},
    "ticker": {"ticker", "symbol", "stock_symbol", "stock_ticker", "ticker_symbol"},
    "revenue": {"revenue", "total_revenue", "revenues"},
    "sales": {"sales", "net_sales", "total_sales", "sales_revenue"},
    "profit": {"profit", "gross_profit", "operating_profit"},
    "net_income": {"net_income", "netincome", "net_profit", "profit_after_tax", "pat", "earnings"},
    "expenses": {"expenses", "total_expenses", "operating_expenses", "opex"},
    "assets": {"assets", "total_assets"},
    "liabilities": {"liabilities", "total_liabilities"},
    "equity": {"equity", "shareholders_equity", "stockholders_equity", "shareholder_equity"},
    "debt": {"debt", "total_debt", "long_term_debt"},
    "cash": {"cash", "cash_and_equivalents", "cash_balance", "cash_and_cash_equivalents"},
    "eps": {"eps", "earnings_per_share"},
    "price": {"price", "close_price", "closing_price", "share_price", "stock_price"},
    "volume": {"volume", "trading_volume", "shares_traded"},
}

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_column_name(name: str) -> str:
    """Lowercase, strip, collapse any run of non-alphanumeric characters to
    a single underscore. `"Net Income ($)"` -> `"net_income"`.
    """
    lowered = str(name).strip().lower()
    collapsed = _NON_ALNUM.sub("_", lowered).strip("_")
    return collapsed


def build_normalization_mapping(columns: list[str]) -> tuple[dict[str, str], list[dict]]:
    """Match each source column against known canonical variants.

    Returns (mapping, ambiguous) where:
      - mapping: source_column -> canonical_concept, for unambiguous 1:1 matches only.
      - ambiguous: list of {"canonical_concept", "source_columns"} for concepts
        matched by more than one source column in this dataset — none of
        those columns are renamed.
    """
    normalized_to_original: dict[str, list[str]] = {}
    for original in columns:
        normalized_to_original.setdefault(normalize_column_name(original), []).append(original)

    concept_to_sources: dict[str, list[str]] = {}
    for concept, variants in CANONICAL_COLUMN_VARIANTS.items():
        matches: list[str] = []
        for variant in variants:
            matches.extend(normalized_to_original.get(variant, []))
        if matches:
            concept_to_sources[concept] = matches

    mapping: dict[str, str] = {}
    ambiguous: list[dict] = []
    for concept, sources in concept_to_sources.items():
        if len(sources) == 1:
            mapping[sources[0]] = concept
        else:
            ambiguous.append({"canonical_concept": concept, "source_columns": sources})

    return mapping, ambiguous
