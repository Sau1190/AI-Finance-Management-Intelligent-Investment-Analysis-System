# Architecture (Phase 9)

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
  └── /api/risk/{symbol}         Phase 9 market-risk metrics from stored prices
        |
        ├── Service layer        validation, processing, export, PDF extraction,
                                 fundamental analysis, market data, technical analysis,
                                 sentiment analysis, risk analysis
        ├── PostgreSQL           file, processing, export, extraction, and analysis metadata
        └── Local storage        original uploads (read-only after upload),
                                 generated exports, generated PDF extracts,
                                 generated analysis metrics, market price files
```

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
- Secrets come from environment variables.

Frontend status: the React page currently displays backend health only. Upload, export, PDF extraction, fundamental-analysis, market-data, technical-analysis, sentiment, and risk controls are not implemented in the frontend; those features exist only as backend API endpoints.
