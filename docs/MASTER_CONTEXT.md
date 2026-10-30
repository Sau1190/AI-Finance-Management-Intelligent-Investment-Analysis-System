# Master context — AI Finance Management

Last updated: 2026-10-27

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
- ML (much later): scikit-learn; XGBoost only if justified

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

Phase 9 — Risk analysis (backend). The backend now covers: file
upload/validation/storage (Phase 1); deterministic Excel/CSV processing
(Phase 2); formatted `.xlsx` export (Phase 3); deterministic PDF text/table
extraction (Phase 4); deterministic fundamental ratios and growth (Phase 5);
daily price history from a market data provider (Phase 6: `POST/GET
/api/market-data/{symbol}`); technical indicators from stored prices (Phase 7:
`POST/GET /api/technical/{symbol}`); headline sentiment (Phase 8: `POST
/api/sentiment/{symbol}/text|news`, `GET /api/sentiment/{symbol}`); and, new in
Phase 9, market-risk metrics from stored prices — daily/annualized volatility,
maximum and current drawdown, best/worst day, historical VaR/CVaR (95%), and
beta/correlation against an optional benchmark (`POST/GET /api/risk/{symbol}`).

Phase 9 is descriptive only — nothing is labelled high/low risk. Definitions are
documented and checked against pandas/numpy; a metric without enough history is
NOT_COMPUTABLE rather than approximated (the 20/100/60-return floors are
reliability judgements, not statistical standards); undefined values stay
undefined; and because prices are unadjusted, a single-day move over 30% raises
a possible-stock-split warning without repairing the data. Phases 6-8 follow the
same honesty rules: prices are accepted as received or rejected with a reason;
sentiment is a transparent word-list method whose accuracy has NOT been measured
(no signal is not neutral); API keys never reach responses, the database, stored
files, or logs.

**Live provider calls are unverified:** the build environment has no outbound
access, so the Alpha Vantage (prices) and NewsAPI (news) adapters were tested
against simulated transports using the vendors' documented response shapes
only; risk, technical, and sentiment results were verified on stored/test data.

412/412 backend tests pass (23 Phase 0/1 + 26 Phase 2 + 16 Phase 3 + 22 Phase 4
+ 35 Phase 5 + 81 Phase 6 + 43 Phase 7 + 108 Phase 8 + 58 Phase 9), verified in
a clean virtualenv install. The frontend currently displays backend health only;
upload, export, PDF extraction, fundamental-analysis, market-data,
technical-analysis, sentiment, and risk controls are not implemented there.
Market data, sentiment, and risk are not yet connected to uploaded files or to
each other. No scoring or LLM is implemented. See `docs/AI_HANDOFF.md`,
`docs/RISK_MODULE.md`, `docs/SENTIMENT_MODULE.md`, `docs/TECHNICAL_MODULE.md`,
`docs/MARKET_MODULE.md`, `docs/FUNDAMENTAL_MODULE.md`, `docs/EXCEL_MODULE.md`,
`docs/PDF_MODULE.md`, and `docs/ROADMAP_QUICK.md`.
