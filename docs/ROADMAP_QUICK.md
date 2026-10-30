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
| 9 | Risk analysis | **Current completed phase** — verified (maths checked against pandas/numpy); descriptive only, no risk labels; see `AI_HANDOFF.md` and `RISK_MODULE.md` |
| 10 | Explainable scoring | Not started |
| 11 | What–How–Why engine | Not started |
| 12 | Dashboard | Not started |
| 13 | ML experimentation | Not started |
| 14 | Testing & security hardening | Not started |
| 15 | Deployment & full documentation | Not started |

A folder existing does **not** mean a phase is complete. Check implementation, tests, and `AI_HANDOFF.md`.
