# Architecture (Phase 14)

```
Browser (React/Vite; backend health display only)
        |
        | HTTP
        v
FastAPI
  ├── /api/health
  ├── /api/files                 upload and file metadata
  ├── /api/files/{id}/process    Phase 2 Excel/CSV processing
  ├── /api/files/{id}/export     Phase 3 workbook generation and download
  ├── /api/files/{id}/extract    Phase 4 PDF text/table extraction
  ├── /api/files/{id}/fundamentals  Phase 5 ratios and growth from processed data
  ├── /api/market-data/{symbol}  Phase 6 daily prices from a market data provider
  ├── /api/technical/{symbol}    Phase 7 technical indicators from stored prices
  ├── /api/sentiment/{symbol}    Phase 8 headline sentiment (submitted text or news)
  ├── /api/risk/{symbol}         Phase 9 market-risk metrics from stored prices
  ├── /api/scores/{symbol}       Phase 10 explainable summary score from Phases 5/7/8/9
  ├── /api/scores/{symbol}/explanation  Phase 11 What-How-Why explanation of the latest score
  └── /api/scoring-method        Phase 10 the scoring method, weights and limits
        |
        ├── Service layer        validation, processing, export, PDF extraction,
                                 fundamental analysis, market data, technical analysis,
                                 sentiment analysis, risk analysis, scoring
        ├── PostgreSQL           file, processing, export, extraction, and analysis metadata
        └── Local storage        original uploads (read-only after upload),
                                 generated exports, generated PDF extracts,
                                 generated analysis metrics, market price files
```

Phase 13 (outside the request path): `backend/ml_experiments/` is an offline, experimental command-line package (scikit-learn, optional `requirements-ml.txt`). It is deliberately NOT part of the diagram above: no route, no service, no table, no import from `app/` into it or back (a test enforces that `app/` never imports it), and it saves no models. See `docs/ML_EXPERIMENTS.md`.

Rules:

- Routes stay thin; services own business logic.
- Pydantic schemas define API shapes and SQLAlchemy models define persisted metadata.
- Original uploads are never overwritten. Cleaned CSVs and generated workbooks live in the exports directory; extracted PDF text and tables live in the separate extracts directory.
- Export formats verified Phase 2 data. It does not calculate financial metrics or create placeholder analysis sheets.
- PDF extraction reads literal text and tables only: no OCR and no financial interpretation. A result is COMPLETE only if every artifact it describes was saved; a storage failure fails the whole run and removes the artifacts already written for it.
- Fundamental analysis reads only Phase 2's cleaned data and computes ratios/growth deterministically: a ratio needs a denominator > 0, concepts (e.g. sales vs revenue) are never substituted, and every skip is reported with a reason. It makes no judgement of good/bad. Like PDF extraction it is all-or-nothing: a storage failure fails the run and removes the artifacts already written.
Market data is fetched through a provider adapter (Alpha Vantage). Adapters only fetch and reshape; shared validation accepts a bar exactly as received or rejects it with a counted reason, and nothing is estimated or repaired. The provider API key travels in the request URL, so errors are mapped to fixed messages, `httpx` request logging is silenced, redirects are not followed, and the key never appears in responses, the database, stored files, or logs. Provider failures are recorded as FAILED snapshots; a COMPLETE snapshot always has its stored file.
Technical analysis reads only stored, validated Phase 6 prices and computes indicators deterministically with documented definitions (checked against pandas and a published RSI reference). A series without enough history is reported NOT_COMPUTABLE rather than approximated, undefined values stay null, and results never label anything buy/sell/overbought. Each result records the market snapshot it used. Like the other analysis phases it is all-or-nothing: a COMPLETE result always has its stored series.
Sentiment analysis is a transparent word-list method (no LLM, no ML model): each score traces to the exact words and phrases matched, a text with no matched term has no signal rather than a neutral score, duplicates and unusable articles are counted and reported, and results record the lexicon version. Its accuracy has not been measured. News comes through an adapter (NewsAPI) that sends its key in a header, never in the URL; third-party article fields are treated as untrusted data.
Risk analysis reads only stored, validated Phase 6 prices and computes volatility, drawdown, historical VaR/CVaR and beta/correlation with documented definitions (checked against pandas/numpy). Metrics lacking enough history are NOT_COMPUTABLE rather than approximated, undefined values stay undefined, and nothing is labelled high/low risk. Because prices are unadjusted, a single-day move over 30% raises a warning (a possible stock split) but the data is never repaired. Each result records the snapshot(s) it used.
Scoring reads only the stored results of earlier phases and combines them with documented, versioned arithmetic (indicator sub-scores between fixed anchors, equal-weight components by default). Missing inputs are excluded and explained, never filled in; the overall score needs at least 2 components and 50% of the weight; every result carries its inputs, weights, source-result ids, a snapshot of the method, and its limits. The score is an educational summary with no ratings, grades or buy/sell/hold labels, and its anchors are unvalidated judgement. Phase 11 adds a deterministic What-How-Why explanation derived on demand from a stored score by fixed templates (`explanation_builder.py`); it re-derives the overall score as a cross-check, adds no numbers, uses no LLM, and persists nothing.
- Secrets come from environment variables.

Frontend status (Phase 12): a React workspace (`frontend/src`) with a sidebar page per implemented feature, a session-only activity list and a suggested-action input that starts existing workflows — files, processing and report download, PDF extraction, fundamentals, market data, technical, sentiment, risk, score, explanation. `src/api/client.js` is the only code that calls the backend (same-origin `/api`, proxied by Vite to port 8000); it holds no keys or secrets, and nothing is stored in the browser. Pure helpers live in `src/lib` and are unit-tested; pages use one small `useRequest` hook (idle/loading/success/empty/error). No router, state, or chart library. See `docs/DASHBOARD.md`.

Phase 14 (hardening, no new feature): request path is `SecurityHeaders -> CORS -> RequestSizeLimit -> routes`; `core/error_handlers.py` turns any leftover database/unexpected error into the standard `{detail:{code,message}}` envelope; `services/db_safety.py` is the shared commit-or-rollback-and-clean-up helper (used by processing and export). See `SECURITY_TESTING.md`.
