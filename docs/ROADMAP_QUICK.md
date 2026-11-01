# Roadmap (quick)

Normal sequential development. Do not skip ahead unless the student explicitly asks.

| Phase | Name | Status |
| --- | --- | --- |
| 0 | Foundation (repo, FastAPI, React, DB config, health, docs, tests) | Complete; included in the historical 23 Phase 0/1 test baseline |
| 1 | File management (upload, validation, storage, status) | Verified complete — see `AI_HANDOFF.md` |
| 2 | Excel & CSV processing | Verified complete — see `AI_HANDOFF.md` and `EXCEL_MODULE.md` |
| 3 | Excel reporting/export | Verified complete — see `AI_HANDOFF.md` (audit fixes re-verified 2026-10-09) |
| 4 | PDF extraction | Verified complete — see `AI_HANDOFF.md` and `PDF_MODULE.md` |
| 5 | Fundamental analysis | Verified complete — see `AI_HANDOFF.md` and `FUNDAMENTAL_MODULE.md` |
| 6 | Market data adapters | Complete — verified against a simulated provider only (no live call possible in the build environment); see `AI_HANDOFF.md` and `MARKET_MODULE.md` |
| 7 | Technical analysis | Verified complete — verified (maths checked against pandas and a published RSI reference); see `AI_HANDOFF.md` and `TECHNICAL_MODULE.md` |
| 8 | Sentiment analysis | Complete — deterministic word-list baseline, accuracy not measured; live news fetch untested (simulated transport only); see `AI_HANDOFF.md` and `SENTIMENT_MODULE.md` |
| 9 | Risk analysis | Verified complete — verified (maths checked against pandas/numpy); descriptive only, no risk labels; see `AI_HANDOFF.md` and `RISK_MODULE.md` |
| 10 | Explainable scoring | Complete — deterministic and fully traceable; anchors/weights are unvalidated judgement, not advice; see `AI_HANDOFF.md` and `SCORING_MODULE.md` |
| 11 | What–How–Why engine | Complete — deterministic template explanation of a stored score; derived on demand, no LLM; API tests written but not executed in the authoring sandbox (no network) — run them; see `AI_HANDOFF.md` and `EXPLANATION_MODULE.md` |
| 12 | Dashboard | Complete — finance-workspace dashboard for every implemented feature; you report the frontend tests, production build and backend tests passed locally (the assistant's sandbox ran 24 unit tests + a 40-step browser test against a mock API only); see `DASHBOARD.md` and `AI_HANDOFF.md` |
| 13 | ML experimentation | Complete — EXPERIMENTAL, offline only (`backend/ml_experiments`, no API/UI, no stored results). Volatility forecast vs naive baselines: on one real stock (GOOG 2004-08) no ML model clearly beat the trailing-volatility baseline. Sentiment classifier vs the Phase 8 lexicon: harness built and tested, **never run on real data (no labelled dataset)**, no accuracy claimed; see `ML_EXPERIMENTS.md` |
| 14 | Testing & security hardening | **Current completed phase** — audit + fixes for export content, database failure/rollback, error envelope, request size, paths, logs, key handling, CORS/headers and frontend error handling; see `SECURITY_TESTING.md`. Run here and passing: 32 new backend logic tests (27/27 planted faults caught), 18 ML tests, 33 frontend tests, browser test against a mock API. **Not run: the full backend `pytest` suite (FastAPI/SQLAlchemy not installable offline) incl. the new `tests/test_hardening_api.py`, and `npm run build`** — run them. No authentication/rate limiting (local, single-user use only) |
| 15 | Deployment & full documentation | Not started |

A folder existing does **not** mean a phase is complete. Check implementation, tests, and `AI_HANDOFF.md`.
