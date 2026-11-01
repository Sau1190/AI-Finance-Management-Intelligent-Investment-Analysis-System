# AI Finance Management

Explainable financial analysis and investment decision-support system (BCA major project).

This is **not** an automated trading system. It does **not** promise investment returns.

Deterministic Python code is the source of truth for numbers. AI/LLM (later phases) only explains verified results.

## Current phase

**Phase 14 — testing & security hardening is the current completed phase** (`docs/SECURITY_TESTING.md`: what was audited, fixed, run and not run; the API still has no login, so run it on your own computer only). Previous: Phase 13 — ML experiments, EXPERIMENTAL, offline research tooling only** (`backend/ml_experiments`, `docs/ML_EXPERIMENTS.md`): a volatility-forecast experiment and a sentiment-classifier experiment, each compared with the existing deterministic method or a naive baseline. They are not part of the API or the dashboard, store nothing, and never change an analysis or score. Actual result: on one real stock no ML model clearly beat the naive baseline; the sentiment experiment has not been run on real data (no labelled dataset exists), so no accuracy is claimed. Not investment advice.

Phase 12 — Dashboard was the previous phase. A beginner-friendly React
dashboard (`frontend/`) now drives every implemented feature — upload, processing and
Excel report, PDF extraction, fundamentals, market data, technical, sentiment, risk,
scoring and the What–How–Why explanation — with loading/empty/error states and a pinned
educational disclaimer. It is laid out as a finance workspace (sidebar, suggested-action
input, result cards) but is **not a chatbot**: every suggested action runs an existing
backend calculation. See `docs/DASHBOARD.md` (run steps, demo walkthrough, tests,
limits). It was tested against a mock API only; the Vite build and the backend suite
were not run in the authoring sandbox (no network) — see the caveats there.
Phase 11 added the templated What / How / Why explanation of a stored score
(`GET /api/scores/{symbol}/explanation`).
Phases 0–3 provide the foundation, file intake, Excel/CSV processing, and
workbook export; Phase 4 extracts literal text and tables from PDFs; Phase 5
computes deterministic ratios and growth from processed Excel/CSV data; Phase 6
fetches and validates daily prices from a market data provider (Alpha Vantage).
Phase 7 computes standard technical indicators (SMA, EMA, MACD, RSI, Bollinger
Bands, ATR) from those stored prices, reporting each one's definition and
history requirements — descriptive only: no buy/sell signals, scoring, or LLM.
Phase 8 scores the sentiment of headlines you submit, or news fetched from a
news provider (NewsAPI), with a transparent word-list method where every score
traces to the exact words that produced it — no LLM or ML model. Phase 9
computes market-risk metrics from the stored prices — volatility, maximum
drawdown, historical VaR/CVaR, and beta/correlation against an optional
benchmark — descriptive only (no "high/low risk" labels), with a warning when a
single-day move suggests an unadjusted stock split. Phase 10 combines Phases 5,
7, 8 and 9 into one explainable 0-100 summary score: every point traces to its
inputs, missing data is excluded and explained (never filled in), the weights
are visible and changeable, and the full method and its limits are returned by
the API. **It is an educational summary, not investment advice or a
recommendation — it has no buy/sell/hold labels, its reference ranges are
illustrative and unvalidated, and it has not been backtested.**
**Limits you should know:** the word list is a small starter list whose
accuracy has *not* been measured, and **neither the market data nor the news
provider integration was verified against a live service** (no outbound access
in the build environment; simulated transports only). The backend test suite
passes in a clean virtual environment (494 tests; see `docs/AI_HANDOFF.md`).

**The frontend is a demo dashboard** covering every implemented backend feature (see
`docs/DASHBOARD.md`); the same features remain available through the backend API (see
`/docs` when the server is running). It never holds API keys. Market data needs
`ALPHA_VANTAGE_API_KEY` and news sentiment needs `NEWS_API_KEY` in the backend `.env`.

**Quick start on Windows (no Docker):** install Python 3.11+ and Node.js LTS, then
double-click `start_demo.bat` (SQLite demo database; not yet run on Windows by the
author — manual steps are in `docs/DASHBOARD.md`).

## Architecture (simple)

```
React frontend  →  FastAPI backend  →  PostgreSQL
                       ↓
                 Service layer (intake, processing, export, PDF extraction)
```

## Prerequisites

- Python 3.13 (already used to scaffold this project)
- Git
- Node.js LTS (needed to run the React app; install from https://nodejs.org )
- PostgreSQL **or** Docker Desktop (optional for local development; the API starts even if the database is down)

## First-time setup (Windows PowerShell)

From the project root:

```powershell
copy .env.example .env
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest
```

Start the API:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

- http://127.0.0.1:8000
- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/api/health

Optional database:

```powershell
docker compose up -d
```

Then refresh `/api/health`. `database.connected` should become `true`.

Frontend (after Node.js is installed):

```powershell
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173

## Project docs

Read these before changing code:

- `docs/MASTER_CONTEXT.md` — what the project is
- `docs/AI_WORKFLOW.md` — how AI tools should work
- `docs/ROADMAP_QUICK.md` — phases
- `docs/EXCEL_MODULE.md` — Excel plan
- `docs/PDF_MODULE.md` — PDF extraction
- `docs/FUNDAMENTAL_MODULE.md` — fundamental analysis
- `docs/MARKET_MODULE.md` — market data adapters
- `docs/TECHNICAL_MODULE.md` — technical analysis
- `docs/SENTIMENT_MODULE.md` — sentiment analysis
- `docs/RISK_MODULE.md` — risk analysis
- `docs/SCORING_MODULE.md` — explainable scoring (read its limits first)
- `docs/ARCHITECTURE.md` — current architecture
- `docs/AI_HANDOFF.md` — current status for the next session
