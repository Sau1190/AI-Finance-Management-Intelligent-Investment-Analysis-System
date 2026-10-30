# AI Finance Management

Explainable financial analysis and investment decision-support system (BCA major project).

This is **not** an automated trading system. It does **not** promise investment returns.

Deterministic Python code is the source of truth for numbers. AI/LLM (later phases) only explains verified results.

## Current phase

**Phase 9 — Risk analysis (backend) is the current completed phase.**
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
single-day move suggests an unadjusted stock split.
**Limits you should know:** the word list is a small starter list whose
accuracy has *not* been measured, and **neither the market data nor the news
provider integration was verified against a live service** (no outbound access
in the build environment; simulated transports only). The backend test suite
passes in a clean virtual environment (412 tests; see `docs/AI_HANDOFF.md`).

**The frontend currently displays backend health only.** Upload, export, PDF
extraction, fundamental-analysis, market-data, technical-analysis, sentiment, and
risk controls are not implemented there; those features are available through the
backend API (see `/docs` when the server is running). Market data needs
`ALPHA_VANTAGE_API_KEY` and news sentiment needs `NEWS_API_KEY` in `.env`.

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
- `docs/ARCHITECTURE.md` — current architecture
- `docs/AI_HANDOFF.md` — current status for the next session
