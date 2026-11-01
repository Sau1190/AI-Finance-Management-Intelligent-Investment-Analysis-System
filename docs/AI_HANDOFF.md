# AI handoff

- **Date:** 2026-11-01
- **Current phase:** Phase 14 — Testing & security hardening (see `SECURITY_TESTING.md` and the first section below; the full backend pytest suite and `npm run build` were NOT run in the authoring sandbox). Previous: Phase 13 — ML experiments (EXPERIMENTAL, offline only). Before that: Phase 12 — Dashboard, redesigned as a finance workspace (24 unit tests and a 40-step browser test pass against a MOCK API; Vite build, backend suite and live-backend check NOT yet run — see below)
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
- **Phase 9 status:** PASS (412/412 at completion).
- **Phase 13 status:** harness built; 18/18 harness tests pass (`python -m unittest discover -s ml_experiments/tests -t .` in `backend/`; 8 planted faults all caught). One real-data experiment ran (volatility, GOOG 2004-08, one stock): no ML model clearly beat the persistence baseline. The sentiment experiment has NEVER run on real data (no labelled dataset) - no accuracy exists. **Not run by the assistant:** `python -m pytest` (no FastAPI/SQLAlchemy in the sandbox; `current_phase` and `tests/test_health.py` changed 12 -> 13, please run), the frontend production build and 40-step browser test (frontend untouched; `npm test` re-run: 24/24).
- **Phase 12 status:** dashboard built and then redesigned as a finance workspace (`frontend/`, `docs/DASHBOARD.md`). Run here and passing: 24/24 frontend unit tests (`npm test`), 40/40 browser steps (headless Chromium, mock API, two consecutive runs of the final source). **Not run:** `npm run build` (Vite), `python -m pytest` (still unconfirmed for Phases 1-11), `start_demo.bat` on Windows, and anything against the real backend or live providers. Do the manual checklist in `docs/DASHBOARD.md` first.
- **Phase 11 status:** builder logic verified (14/14 framework-free tests run, 5/5 mutations caught). The 9 API tests in `tests/test_explanation.py` and the full pytest suite were **not run** in this session (sandbox had no network, so dependencies could not be installed). Expected total if all pass: 494 + 14 + 9 = 517. Run `python -m pytest` in `backend/` and fix anything that fails before treating Phase 11 as PASS.
- **Phase 10 status:** PASS, with the standing caveat that the score's anchors
  and weights are **unvalidated judgement** (see below). 494/494 tests pass in a
  clean virtualenv install (23 Phase 0/1 + 26 Phase 2 + 16 Phase 3 + 22 Phase 4
  + 35 Phase 5 + 81 Phase 6 + 43 Phase 7 + 108 Phase 8 + 58 Phase 9 + 82 Phase
  10; one harmless upstream `starlette` deprecation warning). (Phase 10 was the
  completed phase at that point.) Note: the
  project zip contains no `.git` directory, so no commit was made here — apply
  these changes to your own repository and commit there.

## What changed in Phase 14 (latest session)

Task: Phase 14 only. The first Phase 14 attempt (an earlier chat) ended without saving anything - the
ZIP handed over was still Phase 13 - so the work was redone from the audit list in that transcript.
Full detail, per-finding table, checks run/not run and limitations: **`docs/SECURITY_TESTING.md`**.

Added: `core/http_safety.py` (request-size + security-header ASGI middleware), `core/error_envelope.py`
+ `core/error_handlers.py`, `services/db_safety.py`, `services/download_names.py`,
`services/upload_reader.py`, `tests/test_hardening_units.py` (32 tests), `tests/test_hardening_api.py`
(7 tests, NOT executed), `frontend/src/lib/crash.js`, `frontend/src/components/ErrorBoundary.jsx`,
`frontend/tests/hardening.test.js` (9 tests), `docs/SECURITY_TESTING.md`. Changed: `main.py`
(middleware, tighter CORS, handlers), `config.py` (keys `repr=False`, `current_phase` 14),
`excel_export.py` (cell cleaning), `export_service.py` / `processing_service.py` (rollback + cleanup +
unexpected-error handling), `file_processing.py` (`delete_export_artifacts`), `routes/files.py`
(bounded read), `routes/export.py` (safe download name), logging calls in `fundamental_service.py` /
`pdf_extraction_service.py`, `frontend/src/api/client.js` (timeouts, unreadable answers),
`lib/errors.js` (hints), `App.jsx` / `main.jsx` (boundary), `tests/test_health.py` (phase 14).
No endpoint, table, dependency, dashboard colour or Phase 13 experiment changed.

Run here: 32 new backend logic tests pass (with sandbox-only stubs for pydantic-settings/SQLAlchemy;
27 planted faults all caught), 18 ML tests, 33 frontend tests, browser test 40/40 on 4 later runs
(first run 39/40, one unidentified step, not reproduced), real-browser check of the error boundary,
esbuild production bundle. **Not run:** `python -m pytest` (whole suite), `npm run build`, real
PostgreSQL, Windows `start_demo.bat`. Owner next steps: run both, tell me any failure in
`test_hardening_api.py` first. Known gaps: no authentication or rate limiting; unexpected 500s
lack CORS headers; dependencies not vulnerability-scanned. Phase 15 was NOT started.

## What changed in Phase 13 (previous session)

Task: Phase 13 only - ML experimentation. Owner constraints: deterministic analysis and
scoring stay the source of truth; ML clearly experimental; no investment recommendations; no
silent replacement; no invented accuracy; no paid APIs / data leaving the machine; do not
touch dashboard colours; no Phase 14. Owner reported Phase 12 frontend tests, production
build and backend tests passed locally (not re-run by the assistant).

Added: `backend/ml_experiments/` (`common.py`, `volatility_experiment.py`,
`sentiment_experiment.py`, `run.py` CLI, `tests/test_ml_experiments.py` with 18 tests),
`backend/requirements-ml.txt` (optional, scikit-learn==1.8.0), `docs/ML_EXPERIMENTS.md`
(scope, data inventory, evaluation, risks, actual results, limitations),
`docs/ml_results/volatility_goog_demo.json` (the one real-data report). Changed:
`current_phase` 12 -> 13 (`config.py`, `tests/test_health.py`), `.gitignore` (ml_reports),
status lines in README / ROADMAP_QUICK / MASTER_CONTEXT / ARCHITECTURE / SENTIMENT_MODULE.
**No frontend, API route, service, model, table or existing-test logic changed; no new
runtime dependency in `requirements.txt`.** Experiments live outside `app/` and `tests/`, so
`python -m pytest` collects exactly what it did before.

Findings: (1) No labelled financial text exists anywhere in the project or sandbox, so the
sentiment experiment cannot report accuracy; it refuses below 200 rows / 30 per class.
(2) Volatility on GOOG (963 samples, 630 out-of-sample days): persistence MAE 0.00589 vs
ridge 0.00615 vs gradient boosting 0.00632 vs historical mean 0.00677; paired 95%
intervals all include 0 -> no evidence ML adds anything over trailing volatility. One
stock, one period, untuned: not a general conclusion.
Test-quality note: two of eight planted faults first escaped the tests (a centred, future-
peeking window and in-sample predictions) because my own leak tests were too weak; both
tests were strengthened and all eight are now caught. One new test also had a bug of mine
(it perturbed the day whose features it was checking) and was corrected.

Owner next steps: run `python -m pytest` in `backend/`; supply a licensed labelled headline
CSV to measure sentiment accuracy; run the volatility experiment on your own stored
(adjusted) prices for several symbols before drawing any conclusion. Phase 14 was NOT
started. Known unchanged gap: Phase 2 still does not recognise a "Total Equity" column.

## What changed in the Phase 12 redesign session (previous)

Task: redesign the Phase 12 frontend as a polished workspace (left sidebar with recent
activity, chat-app-inspired layout, suggested-action input, results as cards/tables/
charts) **without** implying a chatbot or any feature that does not exist, using only the
existing backend APIs. **`backend/` is byte-identical to the uploaded Phase 12 ZIP** (no
endpoint, schema, model, config or test change); `docs/DASHBOARD.md` was rewritten.

Frontend changes: new shell (`App.jsx`, `components/Sidebar.jsx`, `Composer.jsx`,
`Icon.jsx`), a new Overview page replacing Home, restyled pages with page headers, score
ring, sentiment distribution bar and metric tiles, native `<details>` for expandable
sections, and a rewritten `index.css`. The tab strip became sidebar navigation (names no
longer carry numbers). New pure modules `lib/nav.js`, `lib/actions.js`, `lib/activity.js`,
`lib/overview.js`; new hook `useIntent` (lets a suggested action start a workflow on the
page it opens); `useRequest` now logs user-started runs to the session activity.
`api/client.js` is unchanged. Suggested actions: Analyze a file, Check sentiment,
Calculate risk, Score this company, Explain the score; each maps to an existing endpoint
(table in `DASHBOARD.md`). Market-data and news fetches never start automatically
(provider quota). The only text input is the symbol; the screen says it is not a chatbot.

Tests actually run (final source, sandbox 2026-10-31): `npm test` 24/24; browser test
40/40 on two consecutive runs; three planted faults each caught; screenshots reviewed.
Bugs found by that review and fixed: an overview tile stuck on "Loading…" with no file
selected, a clipped chip row, hamburger/close buttons visible on desktop (CSS order), a
duplicated disclaimer lead-in, and a pinned header taking ~25% of a phone screen.
**Not run:** `npm run build` (Vite not installable offline; an esbuild production bundle
did succeed, which is only a proxy), `python -m pytest` (no dependencies installable;
Phase 10/11 totals remain unconfirmed), `start_demo.bat` on Windows, anything against the
real backend or live providers, Firefox/Safari, real phones. Phase 13 was not started.

## What changed in the first Phase 12 session



Baseline: the Phase 11 zip delivered in the previous session (no new attachment
arrived; that zip was the only Phase 11 project on disk). The sandbox again had no
network, so Python dependencies and Vite could not be installed; React 19.2.5, esbuild,
Playwright and Chromium were available locally and were used for testing.

Added: the dashboard (`frontend/src/{App.jsx,context.js,api,hooks,lib,components,pages}`),
`frontend/tests/*.test.js` (13 tests, `npm test`), `frontend/e2e/` (mock API, fixture
generator that runs the REAL backend calculation code, 31-step browser test),
`start_demo.bat`, `docs/DASHBOARD.md`. Changed: `current_phase` -> 12
(`config.py`, `test_health.py`), `.gitignore`, `package.json` (test script only; no new
dependency), status lines in README/ROADMAP/MASTER_CONTEXT/ARCHITECTURE/
SCORING_MODULE/EXPLANATION_MODULE. The old health-only `Home.jsx` was replaced.
No backend endpoint, model, service or database change.

Defects found by testing and fixed: (1) the first sample CSV used "Total Equity",
which Phase 2 does not recognise, so debt-to-equity silently vanished from the demo
score (found by the fixture generator's own check; sample now uses "Shareholders
Equity"); (2) Market tab overflowed a 390px phone screen; (3) numbers split
mid-word in phone tables; (4) the disclaimer could scroll out of view (now sticky, with a
test); (5) duplicated component names in the Explain headings; (6) zero-point entries
in the "most points" lists (hidden in the UI only). One of my own browser tests was
racy (waited for a transient idle text) and was corrected. A deliberate-breakage run
showed three of four planted faults caught at first; the fourth (header disclaimer
removed) was only caught after making the disclaimer sticky and strengthening the test.

Observations for the owner: the Phase 11 backend top-3 driver lists can include
entries worth 0.0 points (the dashboard hides them); Phase 2 recognises only exact
column-name variants (e.g. "Equity", "Shareholders Equity"), so real spreadsheets with
"Total Equity" will lose equity-based ratios until variants are added (not changed here,
out of scope). **Phase 13 (ML experimentation) was not started.**

## Prior phase notes (Phase 11 session, kept for history)

## What changed this session (Phase 11)

Baseline: the uploaded Phase 10 zip (no `.env`/`.venv`/caches/`.git` inside; its
own claim of 494 passing could **not** be re-run here for the same no-network
reason). Added `services/explanation_builder.py` (pure, templates only),
`services/explanation_service.py`, `schemas/explanation.py`, route
`GET /api/scores/{symbol}/explanation` (in `routes/scores.py`),
`tests/test_explanation_builder.py`, `tests/test_explanation.py`,
`docs/EXPLANATION_MODULE.md`; `current_phase` -> 11 (config + `test_health.py`),
frontend label, and README/ROADMAP/MASTER_CONTEXT/ARCHITECTURE/SCORING_MODULE
status lines. No new dependency, no new table, no existing function changed.
No LLM (project rule: deterministic first; an LLM must not invent numbers).
One real bug found by the random-input test and fixed: an indicator with a value
inside an unavailable component has no weight, which crashed the sentence
template. **Phase 12 (dashboard) was not started.**

## Prior phase notes (Phase 10 session, kept for history)

## What changed this session (Phase 10)

**Baseline provenance.** The request referred to an "attached Phase 9 ZIP", but
no new attachment appeared in the uploads folder (only the original project zip
and the old Phase 3 audit zip). The only Phase 9 ZIP on disk was the one
delivered in the previous session (`AI-Finance-Management-Phase9-Verified.zip`
in the outputs folder), so that was used, extracted fresh, checked for stray
`.env`/key files (none), and verified at 412/412 before any change. If you meant
a different Phase 9 ZIP, re-apply these changes to it.

Phase 10 had no pre-existing code (clean slate). Read first: the roadmap,
`MASTER_CONTEXT.md` ("educational investment decision-support system"; scoring
is deterministic Python; an LLM "must not invent numbers... or modify official
scores"), `AI_WORKFLOW.md`, and each phase's module doc and stored fields.
Built `scoring_config.py` (the method as versioned data), `scoring_engine.py`
(pure arithmetic), `scoring_inputs.py` (reads the stored results of Phases
5/7/8/9), `score_service.py`, a `ScoreResult` model, schemas, and
`GET /api/scoring-method`, `POST/GET /api/scores/{symbol}`; `current_phase` →
10; `tests/test_scores.py` (82 tests); `docs/SCORING_MODULE.md`. No new
dependency; results stored inline; **Phase 11 (What–How–Why) was not started** —
the result carries the structured explanation (inputs, anchors, sub-scores,
weights, contributions, reasons, limits), not prose.

Design decisions (all documented in `SCORING_MODULE.md`):
- **Not advice.** No rating/band/grade/signal/recommendation anywhere; a notice
  and eight stated limits are in every result (a test checks the keys and the
  vocabulary). The score is "indicators vs fixed reference ranges I chose".
- **Only period-independent fundamentals** (net margin, debt/equity,
  liabilities/assets). Return ratios and growth are excluded because their size
  depends on annual vs quarterly rows, which the data does not state.
- **Indicator → 0–100 by linear interpolation between a poor and a good anchor,
  clamped**, with `saturated` reported; equal weights within a component; equal
  component weights (25%) by default, as a no-information prior; user weights
  allowed (validated, normalised, stored, flagged).
- **Missing data is excluded and explained, never filled in or treated as 0/50.**
  Component minimums (2 of 3 / 1 of 2 / 1 of 1 / 2 of 3; sentiment needs ≥ 5
  scored texts); overall needs ≥ 2 components and ≥ 50% of the weight (both are
  my judgement). Older periods are never substituted for a missing latest one.
- **Explicit input-choice rules** (latest COMPLETE result per phase; fundamentals
  matched by `ticker` column, `company` only if single-entity; latest period by
  date; ambiguous latest period refused; several worksheets require
  `sheet_name`). Consistency warnings for different price snapshots, different
  as-of dates, and any upstream warning (Phase 9's possible-split warning is
  passed through, values used as stored).
- Every result stores the upstream result ids, the weights used, and a snapshot
  of the method, so it stays reproducible if `scoring_config.py` changes.

Verification: hand-computed worked examples; an independent oracle in the test
file (shares no code with the engine) agreeing on 400 seeded random inputs with
random missing data and weights, and recomputing a full score from raw upstream
numbers through the real pipeline to 1e-9; properties (0–100 bounds, improving a
favourable input never lowers the score, contributions sum exactly). **Thirteen
mutations were each caught.** Finding: the first draft of the suite passed 82/82
on its first run, which was treated as a warning — review found one vacuous
assertion (`… is False or True`) and one too-lenient one; both were replaced
before mutation testing.

**Caveat — the score is unvalidated.** Anchors, thresholds, and equal weights
are illustrative judgement. There is no outcome data in this project, so no
backtest or calibration was possible, and none is claimed. The tests prove the
score is computed exactly as documented and fully explainable, not that it is
meaningful. Scores are comparable only when `contributing_components` and
`weights` match. Every earlier caveat still applies underneath it (live price and
news data never fetched; sentiment accuracy unmeasured; unadjusted prices).

Flags: no frontend; no score history or cross-symbol comparison; inputs are not
age-discounted; fundamentals need an uploaded file with a ticker column (or a
single company); `market_storage.py`, `analysis_storage.py` and
`pdf_extraction.py` still contain near-identical write/rollback helpers; the
Phase 3 `n/a`-becomes-blank issue is still open.

## What changed in Phase 9 (previous session)

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

**Phase 13 — ML experimentation.** Not started. Do not begin without explicit instruction. First run the full backend suite (`python -m pytest` in `backend/`), confirm the Phase 11 API tests pass, and complete the live-backend checklist in `docs/DASHBOARD.md`.

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
