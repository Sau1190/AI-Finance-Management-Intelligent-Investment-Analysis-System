# Fundamental analysis module (Phase 5 — verified complete, 2026-10-11)

Deterministic financial ratios and period-over-period growth computed from
Phase 2's cleaned, normalized data. It states **what** each number is and
**how** it was computed. It does not say whether a number is good or bad
(that is the Phase 10 scoring/explanation work), uses no market data
(Phase 6), reads no PDFs, and uses no LLM.

## Pipeline

1. Upload (Phase 1) → process (Phase 2) — analysis requires a processing result
2. `POST /api/files/{file_id}/fundamentals` takes the file's **latest** Phase 2 result
3. For each worksheet: read its cleaned CSV (read-only), compute metrics
4. Per-row metric values are written to `backend/storage/analysis/` (one CSV per analyzed worksheet, generated non-overwriting names)
5. A `FundamentalAnalysisResult` stores the explainable report and the `processing_result_id` it was based on

## Metrics

Ratios (computed row by row):

| Key | Formula |
| --- | --- |
| `net_profit_margin` | net_income / revenue |
| `profit_margin` | profit / revenue |
| `expense_ratio` | expenses / revenue |
| `return_on_assets` | net_income / assets |
| `return_on_equity` | net_income / equity |
| `debt_to_equity` | debt / equity |
| `liabilities_to_assets` | liabilities / assets |
| `equity_ratio` | equity / assets |
| `price_to_earnings` | price / eps |

Growth: `revenue_growth` and `net_income_growth` = (current − prior) / prior.

## Honesty rules

- **Denominator must be > 0.** Zero or negative denominators (revenue, assets, equity, EPS) are skipped with a stated reason (`non-positive equity`); no negative, infinite, or defaulted value is produced. Growth requires the prior value > 0 (`non-positive prior revenue`).
- **Inputs must be finite numbers.** Blank → `missing <concept>`; any other unparseable text → `non-numeric <concept>`. Currency/percent/comma formatting (`$1,200`, `5%`) is parsed the same way Phase 2 parses it; accounting-style `(1,200)` is **not** guessed to be negative — it is reported non-numeric. Literal text such as `n/a` is non-numeric, not missing.
- **No assumed equivalences.** `sales` is not treated as `revenue`; `profit` is not treated as `net_income`. If a metric's input is absent the metric is `NOT_COMPUTABLE` and the report says why, including when a similarly named column exists.
- **Ambiguity is surfaced.** If Phase 2 flagged several source columns as the same concept (e.g. `Revenue` and `Total Revenue`), that concept is unavailable and the reason names the columns.
- **No silent repair.** Duplicate rows are not removed (both are computed). Rows are never reordered in output: the metrics CSV keeps file order and `row_index`.
- **Growth is date-ordered per entity.** The prior period is the previous row *by date* for the same `ticker` (else `company`; else one series). Rows with an unparseable date, a missing entity, or a date shared with another row of the same entity (`duplicate period`, with a warning) are skipped, never merged. The first period of an entity has `no prior period`. Ambiguous numeric dates are read month-first (pandas default); all dates are compared in UTC.
- **Currency/units are not modelled.** Ratios assume the columns in a row share units.

## Result shape

`FundamentalAnalysisResultResponse`: `id`, `file_id`, `processing_result_id`, `status` (`COMPLETE` | `FAILED`), `created_at`, `error_message`, `worksheets[]`.

Each worksheet: `sheet_name`, `status` (`ANALYZED` | `SKIPPED`), `reason` (when skipped), `row_count`, `recognized_concepts`, `entity_column`, `date_column`, `metrics[]`, `warnings[]`, `preview_rows` (first 5), `metrics_storage_key`.

Each metric: `key`, `label`, `formula`, `inputs`, `status` (`COMPUTED` | `NOT_COMPUTABLE`), `reason`, `computed_count`, `skipped_count`, `skipped_reasons` (reason → row count), `min`, `max`, `mean`.

A worksheet is `SKIPPED` (with a reason) when it is empty, has no cleaned data or the cleaned file cannot be read, has no recognized financial columns, or no metric can be computed from its columns.

## API

- `POST /api/files/{file_id}/fundamentals` — 201 with the result. `FAILED` runs are still 201. 404 `FILE_NOT_FOUND`; 404 `PROCESSING_RESULT_NOT_FOUND` (not processed yet); 400 `UNSUPPORTED_FILE_TYPE` (PDF).
- `GET /api/files/{file_id}/fundamentals` — latest result; 404 `FUNDAMENTAL_RESULT_NOT_FOUND` if never run.

A run is `FAILED` (empty `worksheets`) when the latest processing run did not complete, a metrics file cannot be saved, or analysis fails unexpectedly.

## Completeness and storage failures (all-or-nothing)

Same rule as Phase 4: a result is `COMPLETE` only if every artifact it references was saved. A storage failure or unexpected error on any worksheet fails the whole run, reports no worksheets, and deletes the artifacts that run already wrote (best-effort, confined to the analysis directory). A part-written file removes itself; files are created exclusively. If the result row cannot be saved, its artifacts are deleted and the error propagates. Error text never contains paths or low-level details.

## Configuration

`ANALYSIS_DIR` (default `backend/storage/analysis`) — generated metric CSVs, separate from originals, exports, and extracts.

## Tests

`backend/tests/test_fundamentals.py` (35 tests): hand-computed values for every ratio; per-cause skip counts; formatting and parentheses handling; negative equity and non-positive EPS skipped; duplicates kept; file order preserved; metrics unavailable when inputs missing / `sales`≠`revenue` / `profit`≠`net_income` / ambiguous columns; skipped worksheets; growth in date order, per entity, duplicate periods, invalid dates, non-positive prior, no date column; multi-sheet workbook with an empty sheet; missing cleaned file; failed processing; API 404/400 cases and `processing_result_id` traceability; originals and Phase 2 cleaned files unmodified; storage failure rollback, partial write, unexpected failure, database failure, and deleter safety.

## Known limitations

- Phase 3's export does **not** include these metrics yet (no Financial Metrics sheet); results are available through the API and metrics CSVs only.
- Not linked to Phase 4: PDF tables are not analyzed.
- Only the metrics listed above; no current ratio, quick ratio, or margins that need data the normalizer does not recognize.
- Dates in non-ISO ambiguous formats are interpreted month-first.
- The metrics CSVs are not yet downloadable via the API (storage keys only).
