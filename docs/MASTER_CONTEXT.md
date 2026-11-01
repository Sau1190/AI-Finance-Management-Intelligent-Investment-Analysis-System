# Master context — AI Finance Management

Last updated: 2026-10-29

## What this project is

An **educational investment decision-support system**. A user uploads financial data/documents. The system extracts, cleans, validates, analyzes, scores, and explains results using a What–How–Why framework. It is **not** automated trading and **must not** promise returns.

## Core principle

| Layer | Owns |
| --- | --- |
| Deterministic Python | Extraction, cleaning, validation, calculations, indicators, risk, scoring, database, APIs |
| AI / LLM (later) | Explaining verified results, summaries, What–How–Why wording, Q&A over trusted project data |

The LLM must not invent numbers, replace calculations, override validation, or modify official scores.

## Stack (do not change without a documented reason)

- Frontend: React, JavaScript, HTML, CSS (Plotly later)
- Backend: Python, FastAPI, Pydantic, SQLAlchemy
- Database: PostgreSQL
- Data processing (later): Pandas, NumPy, OpenPyXL, PyMuPDF
- ML (Phase 13, experimental, offline only): scikit-learn, optional (`backend/requirements-ml.txt`); XGBoost not used

## Repository layout

```
AI-Finance-Management/
  backend/app/          FastAPI application
  backend/tests/        pytest
  backend/storage/      uploads and exports (original files never overwritten)
  frontend/             React (Vite)
  docs/                 living project documentation
  docker-compose.yml    optional local PostgreSQL
```

## Architecture

Frontend → FastAPI REST API → Service layer → PostgreSQL

Service areas (implemented over phases): File Processing, User Management, Market Data, Fundamental, Technical, Sentiment, Risk, Scoring, Explanation, Reporting / Excel export.

## Development approach

Normal sequential phases. Quality over speed. One phase at a time. See `ROADMAP_QUICK.md`.

## Current phase

Phase 13 — ML experiments (`docs/ML_EXPERIMENTS.md`): **experimental, offline research tooling** in `backend/ml_experiments/` (volatility forecast vs naive baselines; sentiment classifier vs the Phase 8 lexicon). Nothing in the app imports it; no endpoint, no UI, no stored ML output; the deterministic analysis and the Phase 10 score remain the only source of truth. Actual result: on one real stock (GOOG 2004-08) no ML model clearly beat the trailing-volatility baseline; the sentiment experiment has never run on real data (no labelled dataset) and no accuracy is claimed. Phase 12 — Dashboard (frontend, `docs/DASHBOARD.md`): a React dashboard drives every feature below with loading/empty/error states and a pinned disclaimer; it holds no API keys and adds no backend code. Phase 11 — What–How–Why explanation (backend) added `GET /api/scores/{symbol}/explanation`, a deterministic, template-based What / How / Why explanation of the latest stored score (no LLM; nothing is persisted; see `docs/EXPLANATION_MODULE.md`). Phase 10 (explainable scoring) and earlier: the backend now covers: file
upload/validation/storage (Phase 1); deterministic Excel/CSV processing
(Phase 2); formatted `.xlsx` export (Phase 3); deterministic PDF text/table
extraction (Phase 4); fundamental ratios and growth (Phase 5); daily price
history from a market data provider (Phase 6); technical indicators (Phase 7);
headline sentiment (Phase 8); market-risk metrics (Phase 9); and, new in
Phase 10, one explainable 0-100 summary score per symbol that combines the
stored results of Phases 5, 7, 8 and 9 (`POST/GET /api/scores/{symbol}`,
`GET /api/scoring-method`).

Phase 10 is deterministic arithmetic only (no LLM, no model): each indicator is
placed on 0-100 between a "poor" and a "good" anchor, averaged within its
component, and the components are combined by weights (equal by default,
changeable). Every point traces to its inputs; missing indicators/components
are excluded with a recorded reason and the weights renormalised — never filled
in; the overall score needs at least 2 components and 50% of the weight; each
result stores its inputs, weights, upstream result ids and a snapshot of the
method and limits. **The score is an educational summary — not investment
advice, not a recommendation, not a forecast. It has no buy/sell/hold labels or
ratings, its anchors and weights are illustrative and have NOT been validated
or backtested, and two scores are comparable only if their contributing
components and weights match.** The What-How-Why explanation of a stored
score is Phase 11 (built; see `docs/EXPLANATION_MODULE.md`).

Phases 6-9 follow the same honesty rules (prices accepted as received or
rejected with a reason; indicators lacking history NOT_COMPUTABLE rather than
approximated; sentiment is a transparent word-list method whose accuracy has NOT
been measured; unadjusted prices raise a possible-split warning; API keys never
reach responses, the database, stored files, or logs).

**Live provider calls are unverified:** the build environment has no outbound
access, so the Alpha Vantage (prices) and NewsAPI (news) adapters were tested
against simulated transports using the vendors' documented response shapes
only; every downstream result, including scores, was verified on stored/test
data.

Phase 10 baseline: 494/494 backend tests passed (Phase 11 adds 14 framework-free builder tests, run and passing, and 9 API tests that have NOT been run yet) (23 Phase 0/1 + 26 Phase 2 + 16 Phase 3 + 22 Phase 4
+ 35 Phase 5 + 81 Phase 6 + 43 Phase 7 + 108 Phase 8 + 58 Phase 9 + 82
Phase 10), verified in a clean virtualenv install. The frontend is a
demo dashboard (Phase 12, a sidebar workspace with a page for each feature); it was tested against a
mock API, not yet against the live backend (see `docs/DASHBOARD.md`). The
What-How-Why explanation is a fixed-template backend feature shown on the dashboard's
Explain page; no LLM is implemented. See `docs/AI_HANDOFF.md`, `docs/SCORING_MODULE.md`,
`docs/RISK_MODULE.md`, `docs/SENTIMENT_MODULE.md`, `docs/TECHNICAL_MODULE.md`,
`docs/MARKET_MODULE.md`, `docs/FUNDAMENTAL_MODULE.md`, `docs/EXCEL_MODULE.md`,
`docs/PDF_MODULE.md`, and `docs/ROADMAP_QUICK.md`.

Phase 14 — testing & security hardening (`docs/SECURITY_TESTING.md`): fixes only, no new feature. Standing rules added: log only exception TYPES/codes (never `str(exc)`); every failure answers with `{detail:{code,message}}` and never paths/SQL/keys; a write that touches files + the database goes through `services/db_safety.commit_or_cleanup`; body size is capped before parsing; exported cells are literal, control-character-free text. The API has no authentication: local single-user use only. Phase 15 (deployment) is NOT started.
