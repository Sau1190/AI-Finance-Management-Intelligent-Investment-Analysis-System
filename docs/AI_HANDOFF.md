# AI handoff

- **Date:** 2026-10-27
- **Current phase:** Phase 9 — Risk analysis (verified complete)
- **Phase 0 status:** PASS WITH FIXES (see history below).
- **Phase 1 status:** PASS (see history below).
- **Phase 2 status:** PASS (see history below).
- **Phase 3 status:** PASS. The 2026-10-07 audit fixes (exact integer parsing,
  formula-like strings written as literal text, accurate sheet-name metadata)
  were independently re-verified on 2026-10-09: the full suite passed in a
  clean virtualenv install (65/65 before Phase 4 work began).
- **Phase 4 status:** PASS (87/87 at completion; storage-failure handling
  hardened 2026-10-10 — see the follow-up section below).
- **Phase 5 status:** PASS (122/122 at completion).
- **Phase 6 status:** PASS (203/203 at completion) with one standing caveat —
  **live provider calls were never made** (see the Phase 6 section below).
- **Phase 7 status:** PASS (246/246 at completion).
- **Phase 8 status:** PASS (354/354 at completion) with two standing caveats —
  **sentiment accuracy was not measured** and **live news fetching was never
  run** (see the Phase 8 section).
- **Phase 9 status:** PASS. 412/412 tests pass in a clean virtualenv install
  (23 Phase 0/1 + 26 Phase 2 + 16 Phase 3 + 22 Phase 4 + 35 Phase 5 + 81 Phase 6
  + 43 Phase 7 + 108 Phase 8 + 58 Phase 9; one harmless upstream `starlette`
  deprecation warning). Phase 9 is the current completed phase. The frontend
  displays backend health only; upload, export, PDF extraction,
  fundamental-analysis, market-data, technical-analysis, sentiment, and risk
  controls are not implemented there. Note: the project zip contains no `.git`
  directory, so no commit was made here — apply these changes to your own
  repository and commit there.

## What changed this session (Phase 9)

Phase 9 had no pre-existing code (clean slate). Built `risk_metrics.py` (pure
maths), `risk_report.py` (explainable report), `risk_service.py`, a
`RiskAnalysisResult` model, schemas, and `POST/GET /api/risk/{symbol}`
(`?benchmark=`); `current_phase` → 9; `tests/test_risk.py` (58 tests);
`docs/RISK_MODULE.md`. No new dependency; results are stored inline (no file
artifacts, so no storage-failure paths).

Scope decision: **price-based market risk only** — volatility (daily and
annualized), max/current drawdown, best/worst day, historical VaR/CVaR (95%),
beta/correlation vs an optional benchmark. Fundamentals-based leverage risk is
Phase 5; combining everything is Phase 10. Sharpe/Sortino/alpha were left out
deliberately because they need a risk-free-rate assumption the project does not
hardcode. No "high/low risk" labels (a test guards the vocabulary).

Decisions: simple close-to-close returns; sample (n−1) standard deviation;
252-day annualization (a convention, reported in the output); linear-
interpolation percentile; beta/correlation computed between consecutive
*common* dates so holding periods match when one series has gaps; metrics below
a minimum history are NOT_COMPUTABLE, never approximated (floors: 20 returns for
volatility, 100 for VaR/CVaR, 60 aligned for beta — **judgement-based
reliability floors, not statistical standards**).

**The unadjusted-split problem.** Phase 6 prices are as-traded, so a split looks
like a one-day crash. The data cannot distinguish the two, so nothing is
repaired; any single-day move over 30% (a heuristic) raises a warning stating the
count, the largest move and date, and that metrics may be overstated. The
benchmark is checked under its own name. A result with warnings is still
COMPLETE and computed from the data exactly as stored.

Verification: hand-computed values; **pandas/numpy as independent
implementations** — through the live API, volatility, drawdown and trough date,
VaR, CVaR, worst day, beta, correlation and the aligned-return count (363 with a
benchmark missing days) agreed to 9 decimals; mathematical properties (self-beta
1, 2× returns beta 2, CVaR ≤ VaR). Ten mutations were each caught. Findings:
(1) three of my own first-draft tests were mis-built, not the code — two planted
a "split" without keeping the lower level afterwards (creating a rebound, which
the warning correctly reported as the largest move), one hardcoded −50.0% when
the day's ordinary move stacks with it, one looked in the wrong dict level; all
corrected, plus a new crash-and-rebound test; (2) `1.0 − 0.95` is
`0.050000000000000044` in floating point, which put the VaR percentile at
position 1.0000000000000009 rather than exactly 1.0 and let a CVaR tail-boundary
mutation slip past the hand-computed test — the tail probability is now rounded
so ties behave deterministically and that mutation is caught directly.

Flags: risk metrics are only as good as the stored prices, which have still
never come from a live provider; unadjusted prices and dividend-excluded returns;
beta depends entirely on the benchmark chosen; not linked to fundamentals,
sentiment, or uploaded files; `market_storage.py`, `analysis_storage.py` and
`pdf_extraction.py` still contain near-identical write/rollback helpers; the
Phase 3 `n/a`-becomes-blank issue is still open.

## What changed in Phase 8 (previous session)

The sandbox was reset between sessions; the working copy was restored from the
delivered Phase 7 zip and re-verified (246/246) before any new work.

Phase 8 had no pre-existing code (clean slate). The project's own rules
(`AI_WORKFLOW.md`: "No LLM before deterministic analysis works"; ML
experimentation is Phase 13) fixed the approach: a **deterministic, explainable
word-list scorer**, no LLM, no model, no new dependency. Built
`sentiment_lexicon.py` (251 words, 44 phrases, versioned), `sentiment_engine.py`
(pure scoring, negation, phrases, aggregation), `news_providers.py` (NewsAPI
adapter), `sentiment_service.py`, a `SentimentResult` model, schemas, and
`POST /api/sentiment/{symbol}/text`, `POST .../news`, `GET /api/sentiment/{symbol}`;
settings `NEWS_PROVIDER`, `NEWS_TIMEOUT_SECONDS`, `NEWS_PAGE_SIZE`;
`current_phase` → 8; `tests/test_sentiment.py` (108 tests);
`docs/SENTIMENT_MODULE.md`. Results are stored inline (no file artifacts, so no
storage-failure paths).

Decisions: score = (P − N)/(P + N) with ±1/±2 term weights; **a text with no
lexicon term has no signal (null), never a neutral 0**; the aggregate reports
`coverage` and per-label `counts` because a neutral mean can hide disagreement;
exact-duplicate headlines are counted once and the removal is reported;
unusable articles (no title / `[Removed]`) are skipped and counted; zero
articles is a successful empty result (unlike Phase 6, where an empty price
series is a failure); the news key is sent in the `X-Api-Key` **header**, never
the URL; third-party URLs/dates are sanitised (only http(s) links kept).

**Caveat 1 — accuracy unmeasured.** The lexicon is a small hand-written
starter list. There is no labelled financial dataset in the sandbox, so no
accuracy figure exists and none is claimed. The tests prove the scoring is
*correct and explainable*, not that it is *right about real news*. Recommended
next step for accuracy: evaluate against a labelled set (e.g. Financial
PhraseBank) in Phase 13 and compare with an ML model.

**Caveat 2 — live fetch untested.** No outbound access in the sandbox; the
NewsAPI adapter was verified only against `httpx.MockTransport` with the
documented response shape (including `[Removed]` placeholders, which I recall
from the vendor's documentation but could not observe). Do one real fetch and
read the headlines. Also check NewsAPI's current terms: as I recall the free
plan is restricted to development use and delays articles.

Tests: eight mutations (no-signal→neutral, wider negation window, negation
across sentences, shortest-phrase-first, no dedup, key in URL, any URL scheme,
no-signal counted as 0 in the mean) were each caught. Two limitations are
pinned by tests so a future improvement is deliberate: negators more than 3
tokens away are missed, and context is not understood ("rising costs" scores
positive). One test I wrote mis-specified its own sentence (the negator was 4
tokens away, outside the documented window); the engine was right and the test
was corrected.

Flags: ambiguous tickers (`T`, `ON`, `A`) match unrelated news — pass a company
name as `query`; sentiment is not linked to uploaded files, market data, or
technical analysis; `market_storage.py`, `analysis_storage.py` and
`pdf_extraction.py` still contain near-identical write/rollback helpers; the
Phase 3 `n/a`-becomes-blank issue is still open; prices/indicators remain
unadjusted for splits.

## What changed in Phase 7 (previous session)

Phase 7 had no pre-existing code (clean slate). Built
`technical_indicators.py` (pure maths: SMA, EMA, MACD, RSI, Bollinger, ATR),
`technical_report.py` (indicator registry and explainable report),
`technical_service.py`, a `TechnicalAnalysisResult` model, schemas, and
`POST/GET /api/technical/{symbol}` + `GET .../series`; `current_phase` → 7;
`tests/test_technical.py` (43 tests); `docs/TECHNICAL_MODULE.md`. No new
dependency. Indicator series are stored through the existing
`analysis_storage` module (Phase 5) — this avoided a fourth copy of the
exclusive-write/rollback helpers; one additive function, `read_csv_rows`, was
added to it (no existing behaviour changed).

Verification (the point of this phase, since indicator bugs are silent):
hand-computed values for small inputs; **pandas** as an independent
implementation for SMA and Bollinger (population std); and a **published
external RSI(14) reference series** reproduced exactly (70.53, 66.32, 66.55,
69.41, 66.36, 57.97). A first check against the same data rounded to 2
decimals differed by ~0.07 — the reference uses 4-decimal closes; with those
the match is exact, so that was input precision, not a code defect. Five
mutations (RSI without Wilder smoothing, sample instead of population
deviation, ATR ignoring the previous close, EMA seeded with the first value,
SMA(200) allowed on 50 bars) were each caught by the tests. One vacuous
assertion (`... or True`) written in the first draft of a test was found and
removed before completion.

Decisions: definitions are the textbook ones with every ambiguous choice
documented (SMA-seeded EMA, Wilder smoothing, population deviation); a series
without enough bars is NOT_COMPUTABLE and absent from the CSV — never
approximated with a shorter window; RSI with no movement is undefined (null),
never 50; a result records the `market_snapshot_id` it used; the latest
*successful* market snapshot is used even if a newer fetch failed; no
buy/sell/overbought vocabulary (a test guards this).

Practical note for users: Phase 6's default `compact` history is ~100 bars, so
`sma_200` is NOT_COMPUTABLE unless the data is fetched with `?history=full`.

Flags: `market_storage.py`, `analysis_storage.py` and `pdf_extraction.py` still
contain near-identical write/rollback helpers (the shared-module cleanup
recommended earlier remains open); the Phase 3 `n/a`-becomes-blank issue is
still open; indicators use unadjusted prices, so a stock split distorts them.

## What changed in Phase 6 (previous session)

Phase 6 had no pre-existing code (clean slate). Built `AlphaVantageProvider`
(adapter), provider-independent bar validation, a storage module, a
`MarketDataSnapshot` model, schemas, `market_service`, and
`POST/GET /api/market-data/{symbol}` + `GET .../prices`; settings
`MARKET_DATA_PROVIDER`, `MARKET_DATA_TIMEOUT_SECONDS`, `MARKET_DIR`;
`current_phase` → 6; `tests/test_market_data.py` (81 tests);
`docs/MARKET_MODULE.md`. No new dependency (`httpx` was already present).

**Caveat — live calls unverified.** The sandbox cannot resolve the provider's
host, so the adapter was tested only against `httpx.MockTransport` returning
Alpha Vantage's documented response shape. First real use should be one manual
fetch with a real key, comparing stored bars with the provider's site. The
vendor reports errors inside HTTP 200 bodies (`Error Message`, `Note`,
`Information`); that behaviour is mapped from documentation, not observed. An
unknown symbol and an invalid key are indistinguishable (same `Error Message`
key), so they share one error code.

Decisions: adapters only fetch and reshape; validation is shared and never
repairs (bars rejected with counted reasons, duplicates dropped, future dates
beyond UTC+1 day rejected); a provider problem is a FAILED snapshot (201), but
a missing/unsupported provider configuration is a 503 that records nothing; a
failed fetch does not hide earlier good data (`/prices` serves the latest
*successful* snapshot); a COMPLETE snapshot always has its stored file.

**Security finding fixed during verification:** Alpha Vantage requires the API
key in the URL query string, and `httpx` logs every request URL at INFO. With
INFO logging enabled the key was written to the logs (responses and database
were clean). The adapter now pins the `httpx`/`httpcore` loggers to WARNING;
errors never carry exception text (`from None`), the service logs only codes or
exception types, redirects are not followed, responses are size-capped. Tests
assert the key is absent from responses, database rows, stored files, and logs
at DEBUG, and mutation checks confirmed those tests fail if the pinning, the
suppression, the high/low validation, or redirect-disabling is removed.
`tests/conftest.py` blanks `ALPHA_VANTAGE_API_KEY` so tests can never use a
developer's real key from `.env`.

**Repository hygiene fix:** `.gitignore` only ignored `storage/uploads` and
`storage/exports`; the `extracts`, `analysis` (Phases 4–5) and new `market`
directories were not ignored, so generated PDF text, analysis data, and price
files could have been committed. Added the three patterns.

Flags: configuration errors (503) are checked before input validation, so an
unconfigured server answers 503 even for a bad symbol. `analysis_storage.py`,
`market_storage.py` and `pdf_extraction.py` now contain near-identical
exclusive-write / rollback helpers — a shared module is the recommended cleanup
before Phase 7. The Phase 3 `n/a`-becomes-blank issue (below) is still open.

## What changed in Phase 5 (previous session)

Phase 5 had no pre-existing code (clean slate). Built:

1. `app/services/fundamental_metrics.py` — pure calculations over a Phase 2
   cleaned-data DataFrame: 9 ratios and 2 growth metrics, each reporting
   formula, inputs, computed/skipped counts and per-cause skip reasons.
2. `app/services/fundamental_service.py` — orchestration: latest Phase 2
   processing result → each worksheet's cleaned CSV → metrics → per-worksheet
   metrics CSV in `storage/analysis/` → persisted `FundamentalAnalysisResult`
   (records `processing_result_id`). All-or-nothing with rollback (same rule as
   Phase 4), including database-failure rollback.
3. `app/services/analysis_storage.py` (exclusive writes, partial-write cleanup,
   confined best-effort deleter), model, schema, `AnalysisRequestError`,
   `POST/GET /api/files/{file_id}/fundamentals`, `ANALYSIS_DIR` setting,
   `current_phase` → 5 (health tests updated), `tests/conftest.py` isolates
   `ANALYSIS_DIR`.
4. `tests/test_fundamentals.py` — 35 tests; `docs/FUNDAMENTAL_MODULE.md`.

Design decisions (deliberate, documented in `FUNDAMENTAL_MODULE.md`):
- A ratio needs a denominator > 0; otherwise the row is skipped with a reason
  (no negative/infinite/defaulted values). Growth needs prior value > 0.
- `sales` is not assumed to be `revenue`, `profit` is not assumed to be
  `net_income`; absent or ambiguous inputs make a metric NOT_COMPUTABLE with an
  explanation.
- No de-duplication or reordering; growth is date-ordered per ticker/company;
  duplicate periods and invalid dates are skipped and reported.
- No good/bad judgement (Phase 10), no market data (Phase 6), no PDF input.

Verification: realistic multi-ticker data was run through the live API first
and every number checked by hand (e.g. BBB net income growth (40−5)/5 = 7.0).
That run exposed one real bug, fixed before tests were written: reading the
cleaned CSV with pandas defaults turned literal text such as `n/a` into NaN,
relabelling a non-numeric value as "missing" and disagreeing with Phase 2's
own missing-value rule; the reader now treats only blank cells as missing.
Mutation checks (growth ordered by file order; zero denominators allowed) were
both caught by the new tests.

## Known issues / flags for the next session

- **Phase 3 (not changed here):** `export_service._read_cleaned_df` uses
  `pd.read_csv(path, dtype=str)` with pandas' default NA handling, so a literal
  `n/a` / `NA` / `null` cell in the cleaned data would appear blank in the
  exported Cleaned sheet. Same root cause as the Phase 5 bug above; a
  one-line fix (`keep_default_na=False, na_values=[""]`) plus a test was left
  for an explicit decision because it changes a previously verified phase.
- `analysis_storage.py` deliberately duplicates the small exclusive-write /
  rollback helpers in `pdf_extraction.py` rather than refactoring Phase 4;
  consolidating them into one shared module is a reasonable later cleanup.
- Phase 3's export does not yet include fundamental metrics, and metrics CSVs
  are not downloadable through the API (storage keys only).

## Follow-up fix (2026-10-10): storage failures can no longer yield COMPLETE

Problem: if saving a page's extracted text or a table failed, the service only
appended a warning and could still report the run `COMPLETE`, with pages
pointing at missing (or no) files.

Chosen outcome — all-or-nothing:
- Saved text/table files are required. Any save failure (or an unexpected
  page-extraction failure) makes the run `FAILED` with `pages=[]`, the true
  `page_count`, and a generic `EXTRACTION_STORAGE_FAILURE` message naming the
  page. Still HTTP 201, consistent with other failed runs; no paths or
  low-level errors are exposed.
- Artifacts already written during that run are deleted
  (`pdf_extraction.delete_artifacts`, best-effort, never raises, confined to
  the extracts directory).
- A write that fails part-way removes its own truncated file; files are created
  exclusively so nothing is overwritten.
- If the result row cannot be saved to the database, its artifacts are deleted
  and the error propagates.
- Table *detection* stays best-effort (warning, text kept) — only *saving* is
  required.

Files changed: `backend/app/services/pdf_extraction.py` (shared exclusive
writer, cleanup, `delete_artifacts`), `backend/app/services/pdf_extraction_service.py`
(fail-and-rollback logic), `backend/tests/test_extraction.py` (+9 regression
tests; confirmed they fail against the old warn-only behaviour).

Status references aligned to "Phase 4 is the current completed phase; frontend
shows health only": `README.md`, `docs/ARCHITECTURE.md`,
`frontend/src/pages/Home.jsx` (label), `docs/ROADMAP_QUICK.md`,
`docs/MASTER_CONTEXT.md`, `docs/PDF_MODULE.md`, and the stale "re-verification
pending" wording in `docs/EXCEL_MODULE.md`'s Phase 3 section.

## What changed this session (Phase 4)

Phase 4 had no pre-existing code (clean slate). Built, in this order:

1. `pymupdf==1.28.2` added (import name `pymupdf`; the `fitz` alias is deprecated).
2. `app/services/pdf_extraction.py` — low-level: opens PDF bytes, detects
   encrypted (never guesses a password) and unparseable files, extracts
   literal text per page and tables via `Page.find_tables()`, and writes
   full text/tables to `storage/extracts/` under generated names that never
   overwrite (same guarantee as Phase 2/3 artifacts).
3. `app/services/pdf_extraction_service.py` — orchestration: validates the
   file is a PDF, reads the original read-only, enforces `max_pdf_pages`,
   builds per-page reports with bounded previews (500 chars of text, first 5
   table rows; full content always in storage), persists a
   `PdfExtractionResult`.
4. `app/api/routes/extraction.py` — `POST /api/files/{file_id}/extract` (201,
   including FAILED runs) and `GET /api/files/{file_id}/extract` (latest result,
   404 `EXTRACTION_RESULT_NOT_FOUND` if never extracted).
5. Model `pdf_extraction_result.py`, schema `pdf_extraction.py`,
   `ExtractionRequestError`, settings `extracts_dir` / `max_pdf_pages`
   (default 200), `current_phase` bumped to 4 (health tests updated).
6. `tests/conftest.py` isolates `EXTRACTS_DIR` per test.

Behaviors worth knowing:
- A page with no text layer is reported with a warning (OCR is explicitly not
  performed), not an error, and no empty text file is written.
- Encrypted, corrupt, and over-limit PDFs yield a `FAILED` result (HTTP 201)
  with a generic message; internals are logged server-side only.
- Over-limit PDFs are reported (`PDF_TOO_LARGE`, true `page_count`) and not
  partially extracted — no silent truncation.
- Table detection is best-effort; a table-detection failure on a page adds a
  warning and never blocks that page's text. (Saving extracted text/tables is
  NOT best-effort — see the follow-up fix above.)

Manual smoke tests (real multi-page PDF with a table, blank page, encrypted,
corrupt, over-limit, wrong file type, missing file, GET-before-extract) were
run through the live API before the test suite was written; all behaved as
described above and the original file stayed byte-identical.

## Files created/modified (Phase 4)

Created: `backend/app/models/pdf_extraction_result.py`,
`backend/app/schemas/pdf_extraction.py`,
`backend/app/services/pdf_extraction.py`,
`backend/app/services/pdf_extraction_service.py`,
`backend/app/api/routes/extraction.py`, `backend/tests/test_extraction.py`,
`docs/PDF_MODULE.md`

Modified: `backend/requirements.txt`, `backend/app/core/config.py`,
`backend/app/core/database.py`, `backend/app/core/exceptions.py`,
`backend/app/api/router.py`, `backend/tests/conftest.py`,
`backend/tests/test_health.py`, `docs/AI_HANDOFF.md`,
`docs/MASTER_CONTEXT.md`, `docs/ROADMAP_QUICK.md`

## Known limitations (Phase 4)

- No OCR: scanned/image-only PDFs yield no text (warned, not guessed).
- Table detection relies on PyMuPDF's ruling/alignment heuristics; borderless
  or irregular tables may be missed or split. Extracted tables are literal
  cell text only — no header detection, typing, or normalization yet.
- Extraction is not yet linked to Phase 2's financial-column normalization;
  interpreting PDF tables as financial data belongs to later phases.
- Text is stored one file per page; very large PDFs create many small files
  (bounded by `max_pdf_pages`).
- The `pymupdf_layout` package (optional, suggested in PyMuPDF's own log
  output) was deliberately not added.

## Next phase

**Phase 10 — Explainable scoring.** Not started. Do not begin without explicit instruction.

---

## Prior phase notes (Phase 3 session, kept for history)

## What changed this session (Phase 3)

### Follow-up audit fixes (2026-10-07)

1. Integer cells now use exact decimal parsing and remain text if fractional
   or non-finite, avoiding float precision loss and silent truncation.
2. Imported strings and headers are explicitly written as literal text in
   workbook cells, so values beginning with `=` cannot become formulas.
3. Export metadata now uses the same title generation as the workbook and
   reports the actual sheet names in workbook order.
4. Added regression tests for fractional/large integers, formula-like CSV
   cells, and exact sheet metadata. Updated the roadmap and app status labels.
5. The test suite could not be run here: system Python lacks the project
   dependencies, and the bundled Python runtime also lacks them. No packages
   were installed.

Audited the existing code before trusting it, per this project's established
pattern — including a prior session's own commit claiming Phase 3 was
"verified complete." Found:

1. **Regression against Phase 2**: an incomplete edit to `file_processing.py`
   had deleted `save_cleaned_csv`'s `def` line entirely — its body survived
   only as unreachable dead code merged into the new `save_export_workbook`.
   Every Phase 2 processing run would have hit `AttributeError` on save.
   Fixed (by the prior session) by restoring `save_cleaned_csv` as its own
   function; independently reran the full Phase 0–2 suite to confirm.
2. The `excel_export.py` builder was well-scoped: it deliberately produces
   only **Summary / Raw Data / Cleaned Data** sheets and explicitly declines
   to fabricate Financial Metrics, Market/Technical indicators, Sentiment,
   Risk, or Scores. Kept as-is.
3. **Found by this session, not caught by the existing 62 tests**: exported
   a real workbook through the actual API and opened it with `openpyxl` to
   inspect cell types directly (not just headers) — every "Cleaned" sheet
   cell for a normalized column (Revenue, Date, Net Income, …) was plain
   text (`'5000'`), not a real Excel number/date, so the number formats and
   sort/filter behavior the code's own docstring promised never actually
   applied. Root cause: Phase 2 renames a normalized column's header in the
   cleaned CSV to its canonical concept (`"Revenue"` → `"revenue"`), but
   `export_service._build_worksheet_exports` keyed `column_types` by the
   *original* source name, so the lookup in `excel_export._write_cleaned_sheet`
   always missed for exactly the columns that matter most. Fixed by keying
   on `canonical_concept or name` — the actual final header. Added
   `test_export_cleaned_sheet_uses_real_typed_cells_for_normalized_columns`
   so this can't silently regress again; none of the other 62 tests would
   have caught it since they check headers/values, not cell *types*.

## Files created/modified (Phase 3)

Created:
- `backend/app/services/export_service.py` — reads Phase 2's `ProcessingResult`,
  re-reads the original file and Phase 2's cleaned CSVs, hands real data to
  `excel_export.build_workbook`, persists an `ExportResult`
- `backend/app/api/routes/export.py` — `POST/GET /api/files/{file_id}/export`,
  `GET /api/files/{file_id}/export/download`
- `backend/tests/test_export.py` — 16 tests (imports Phase 2's `build_xlsx`/
  `big_upload_limit`/`XLSX_MIME` rather than duplicating them)

Modified:
- `backend/app/services/file_processing.py` — fixed the `save_cleaned_csv` regression
- `backend/app/services/export_service.py` — fixed the column_types key mismatch (this session)
- `backend/app/api/router.py` — wired in the new route
- `docs/AI_HANDOFF.md`, `docs/MASTER_CONTEXT.md`, `docs/ROADMAP_QUICK.md`, `docs/EXCEL_MODULE.md`

Already present, audited and kept as-is:
- `backend/app/models/export_result.py`, `backend/app/schemas/export.py`,
  `backend/app/services/excel_export.py`
- `backend/app/core/database.py` (already registered the new model)

## Dependencies

None added. Uses the same `pandas`/`openpyxl` from Phase 2.

## Tests

```bash
cd backend
python -m pytest
```

The previous archive recorded **63 passed, 0 failed** on 2026-09-15
(23 Phase 0/1 + 26 Phase 2 + 14 Phase 3). That run predates the two new
regression tests and is not a verification of this updated copy; the expected
suite size is now 65. Phase 3 coverage includes single- and
multi-sheet XLSX export (correct per-sheet titles), CSV export, an empty
worksheet correctly shown as `SKIPPED` with no Cleaned sheet, exporting a
`FAILED` processing run (summary-only workbook noting the failure, still a
valid 201 — not a 500), export-before-processing (404), export of a
nonexistent file (404), get-latest-export before any export exists (404),
download without an export (404), original file byte-identical after
export, no internal details leaked in a degraded-export response, and
**Cleaned-sheet cells for normalized columns are real typed Excel
numbers/dates with correct number formats**, not text.

## Known issues

(Carried over from Phase 2, still accurate — see history below.) Additionally:
- Export re-reads the original file from disk on every export request rather
  than caching a parsed version; acceptable at current expected file sizes
  and `max_processing_rows`.
- The frontend currently displays backend health only; upload, export, and
  PDF extraction controls are not implemented there.

## Decisions

(Carried over from Phase 2, still accurate — see history below.) Additionally:
- Export never computes anything Phase 2 didn't already determine — it only
  reformats already-verified data into a workbook.
- A failed processing run still produces a valid (summary-only) export,
  rather than blocking export entirely — the user can see *why* it failed.
- `GET .../export/download` streams the file directly rather than requiring
  a second lookup of the storage key — but `GET .../export` (metadata only)
  is kept as a separate endpoint for API clients that just need the status.

## Next phase (as of the Phase 3 session — superseded by the Phase 4 section above)

Phase 4 (PDF extraction) was subsequently completed; see the top of this file.

---

## Prior phase history (condensed)

**Phase 2** (2026-09-13): Found and fixed 4 real bugs discovered by running
real data through already-present-but-untested code: `is_blank_grid` crashed
on real input (`.str` on a DataFrame); `header_assumed_default` held a NumPy
`bool_` that crashed JSON serialization; bare numbers like `"1000"` were
silently misclassified as dates before numeric detection ran; and
`pandas.read_csv(header=None, on_bad_lines="skip")` silently dropped all data
whenever a CSV started with a one-column title line. Added the full Phase 2
test suite (`test_processing.py`, 26 tests) and fixed a test-isolation gap
(`EXPORTS_DIR` wasn't sandboxed). Verified 49/49 passing at the time.

**Phase 0/1** (2026-09-13, earlier session): Fixed a stale test (`test_health.py`
asserted `phase == 0` after `current_phase` had been bumped to `1`) and a real
XLSX validation gap (`content.startswith(b"PK")` accepted any ZIP file; replaced
with a real OOXML structural check). Added the full Phase 1 test suite
(`test_files.py`, 21 tests) and a global `RequestValidationError` handler so
framework-level errors use the same `{code, message}` envelope as application
errors. Verified 23/23 passing at the time.
