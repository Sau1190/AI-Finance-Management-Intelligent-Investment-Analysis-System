# AI Finance Management — Development Roadmap

## Phase 0 — Requirements + Foundation
Finalize scope, repository, Python environment, FastAPI, React, PostgreSQL, environment configuration and basic tests.

## Phase 1 — File Management
Implement upload, validation, metadata, safe storage and processing status.

## Phase 2 — Excel + CSV Processing
Support XLSX/CSV parsing, multiple sheets, column/header detection, data types, missing/duplicate checks, cleaning and preview.

## Phase 3 — Excel Analysis Export
Generate professional XLSX workbooks containing raw data, cleaned data, financial metrics, market data, technical indicators, sentiment, scores and What–How–Why summary.

## Phase 4 — PDF Extraction + Validation
Extract text/tables from PDFs, normalize financial fields, detect warnings and expose validation status.

## Phase 5 — Fundamental Analysis
Margins, ROE, ROA, current ratio, debt/equity, P/E where applicable, growth and related metrics.

## Phase 6 — Market Integration
Start with one market-data provider and one adapter/normalization layer. Add a news source separately.

## Phase 7 — Technical Analysis
SMA, EMA, RSI, MACD, volatility, price/volume trends and charts.

## Phase 8 — Sentiment
Collect relevant news/headlines and implement a transparent positive/neutral/negative baseline.

## Phase 9 — Explainable Scoring
Create deterministic component scores, configurable weights, evidence trails and risk/warning handling.

## Phase 10 — What–How–Why
Use an LLM to explain verified structured analysis results without changing calculations or scores.

## Phase 11 — Dashboard
Build the React dashboard with stock overview, charts, metrics, scores, warnings and explanations.

## Phase 12 — Reporting
Add PDF/HTML-style analytical reporting and professional Excel export.

## Phase 13 — ML Experimentation
Only where a suitable historical dataset and clearly defined target exist. Compare appropriate models and evaluate with correct metrics. Avoid data leakage.

## Phase 14 — Testing + Security
Unit, API, integration, file-processing, scoring, authentication and security tests.

## Phase 15 — Deployment + Documentation
Deployment, README, architecture diagrams, database diagrams, screenshots, final report, presentation and viva preparation.

## Scope Rule
Build each phase to a stable state before starting the next. Advanced portfolio optimization, automated trading, broker integration, real-time streaming, mobile apps and multiple-LLM architectures remain future scope unless the core system is already complete.
