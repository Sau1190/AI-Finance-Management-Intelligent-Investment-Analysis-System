# Excel module

Excel is a first-class part of this project, not an extra.

## Input (from Phase 1–2)

- `.xlsx` via OpenPyXL / Pandas
- `.csv` via Pandas

Original uploaded workbooks are **never overwritten**. Cleaned copies and reports are written to `backend/storage/exports/`.

## Processing pipeline (Phase 2 — verified complete, 2026-09-13)

1. Upload workbook (Phase 1)
2. Validate file (Phase 1)
3. Locate stored original, read worksheets (XLSX: every worksheet via OpenPyXL/Pandas, `header=None`; CSV: a single synthetic "csv" worksheet)
4. Detect header row (deterministic scoring over the first 10 rows — see below)
5. Detect columns, infer data types (date / integer / float / boolean / string / unknown)
6. Missing-value counts per column
7. Duplicate-row counts
8. Inconsistent-value findings per typed column (count + up to 3 examples)
9. Financial-column normalization (exact-match mapping to canonical concepts)
10. Cleaned data written to `backend/storage/exports/` under a generated name (never overwrites)
11. Structured report persisted as a `ProcessingResult`, returned via API

### Header detection
Scores each candidate row as `0.4 * string_ratio + 0.3 * uniqueness_ratio + 0.3 * non_null_ratio`, with a bonus if the next row is meaningfully more numeric. Falls back to row 0 with `header_assumed_default: true` if nothing scores above 0.5 — callers must treat that as a warning, not a confident result.

### Type inference
Classifies a column as boolean/date/integer/float only when ≥90% of non-null values conform; otherwise "string". Numeric-looking values are never misclassified as dates — bare numbers like `"1000"` are checked against numeric-look before date parsing is attempted (a real bug found and fixed during Phase 2 verification: `pandas.to_datetime` will otherwise happily parse plain numbers as dates).

### Financial-column normalization
`app/services/financial_normalization.py` maps known column-name variants (after lowercasing and collapsing punctuation to underscores) to canonical concepts: `date, company, ticker, revenue, sales, profit, net_income, expenses, assets, liabilities, equity, debt, cash, eps, price, volume`. Matching is **exact only** — no fuzzy matching, no LLM. If two source columns in the same dataset match the same concept, **neither is renamed**; both are reported under `ambiguous_mappings` instead, so no ambiguous rename happens silently.

### CSV specifics
No CSV file has a reliable magic signature, so Phase 1 already relies on structural/content validation rather than a signature check. For parsing: delimiter is sniffed from `,`, `;`, tab, `|` (falls back to comma). Rows are parsed with `csv.reader` and padded to the widest row's column count — **never silently dropped** (a real bug found and fixed: `pandas.read_csv(header=None, ...)` infers column count from row 1 and drops every later row that doesn't match, which silently destroyed all data whenever a CSV started with a one-column title line before its real header).

### Limits
`max_processing_rows` (default 50,000, configurable) caps per-worksheet/CSV processing. Datasets over the limit are reported (`DATASET_TOO_LARGE` in `errors`) with `cleaned_data_status: SKIPPED`, not partially processed.

### API
- `POST /api/files/{file_id}/process` — run the pipeline, 201 with the result (a `FAILED` status for an unreadable file is still a valid 201 result, not a 500)
- `GET /api/files/{file_id}/process` — fetch the latest result, 404 if never processed

**Status:** Phase 2 complete and tested (26 tests, `backend/tests/test_processing.py`).

## Export workbook (Phase 3 — verified complete; audit fixes re-verified 2026-10-09)

`app/services/excel_export.py` builds a formatted `.xlsx` from Phase 2's
already-verified output only:

- **Summary** — one row per worksheet: row/column counts, missing/duplicate/
  inconsistent-value totals, cleaned-data status, warning/error counts, plus
  a bar chart of rows per worksheet. If the underlying processing run
  `FAILED`, this is the only sheet, and states why.
- **Raw Data** (or **Raw - <sheet>** for multi-sheet workbooks) — the
  original grid as read, header row highlighted, frozen panes, autosized columns.
- **Cleaned Data** (or **Cleaned - <sheet>**) — Phase 2's normalized column
  names and cleaned values, with real numeric/date types (not just display
  formatting) so Excel's own sort/filter work correctly, conditional
  highlighting for blanks, filters, frozen header. Integer conversion is
  exact; values that do not conform remain text.

Uploaded strings are written as literal text, including values beginning
with `=`, so workbook export does not turn user data into formulas. Export
metadata reports the same sheet titles and order as the generated workbook.

**Deliberately does not** include Financial Metrics, Market/Stock Metrics,
Technical Indicators, Sentiment, Risk, Scores, or a What–How–Why summary —
those sheets from the original vision below require analysis phases that
don't exist yet, and fabricating them here would mean inventing numbers.
Revisit this module once those phases exist; do not backfill placeholder
values into this workbook in the meantime.

API: `POST /api/files/{file_id}/export` (generate), `GET .../export` (latest
metadata), `GET .../export/download` (stream the `.xlsx`). Never overwrites
the original upload; exports live under `storage/exports/` with a generated
name, same guarantee as Phase 2's cleaned CSVs.

### Original vision (later phases, not yet built)

Professional `.xlsx` with sheets such as:

Raw Data, Cleaned Data, Financial Metrics, Market/Stock Metrics, Technical Indicators, Sentiment, Risk, Scores, What–How–Why Summary.

Use headers, number formats, column widths, freeze panes, filters, conditional formatting, and simple charts where useful.

**Status:** Raw Data / Cleaned Data / formatting above are implemented. The
metrics/sentiment/risk/scores/summary sheets are planned only, pending the
phases that compute them.

The follow-up audit fixes have regression tests and were re-verified on
2026-10-09 in a clean virtual environment. See `AI_HANDOFF.md` for the
current verification status.
