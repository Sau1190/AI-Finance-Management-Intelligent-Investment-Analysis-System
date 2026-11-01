# Dashboard (Phase 12, redesigned as a finance workspace)

A React workspace in `frontend/` that drives every implemented backend feature, so the
project can be demonstrated locally. It is a thin window onto the existing API: it adds
**no backend endpoints, no database tables and no new npm dependencies** (React, Vite and
the React plugin, as before). The layout is inspired by familiar AI chat apps (sidebar,
focused workspace, docked input with suggested actions) but it is **not a chatbot**.

> **Educational use only.** A disclaimer is pinned to the top of the screen at all times
> (a short form on phones) and repeated in full in the footer. Nothing the dashboard shows
> is investment advice, a rating or a forecast.

## What is, and is not, in it

This is a deterministic finance project. Every number comes from a backend calculation.

- **There is no free-form chat, no LLM and no AI-generated answer.** The only text box in
  the input area is the company symbol, and the input area says so on screen.
- The five suggested actions are buttons that each start **one existing backend
  workflow** (table below). Nothing else is promised.
- Explanations (Phase 11) are fixed-template text built from stored numbers.

## Layout

- **Left sidebar** — grouped navigation (Your data, Analysis, Insight), a *New workspace*
  button (clears the selected file, symbol and activity), and **Recent activity**: what
  you ran in this session (kept in memory only — nothing is saved to the browser or server;
  a page reload clears it). Entries link back to the page. On screens narrower than 900 px
  the sidebar becomes a slide-in menu (hamburger button).
- **Top bar** — current page, the selected symbol and the selected file.
- **Workspace** — a page header, then cards: result summaries, tables, charts and
  expandable detail (`<details>` sections for per-text evidence, per-indicator working,
  assumptions and limits).
- **Docked input area** — five suggested actions and the symbol box. Press **Enter** (or
  the arrow button) to open the Overview with the saved results for that symbol.
  The paperclip opens Files.
- **Overview** — latest saved score (ring), a tile per component showing its latest
  saved result (or "Not run yet"), cards for every workflow, a one-click sample-data
  loader, and the backend status card.

### Suggested actions → existing API workflows

| Button | Opens | Calls (existing API) | Starts by itself? |
|---|---|---|---|
| Analyze a file | Process & report (CSV/Excel) or PDF extraction (PDF); Files if none selected | `POST /api/files/{id}/process` or `POST /api/files/{id}/extract` | Yes, when a file is selected |
| Check sentiment | Sentiment | `POST /api/sentiment/{symbol}/text` (after you paste or load headlines) | Opens the page and focuses the headlines box; you press *Score* |
| Calculate risk | Risk | `POST /api/risk/{symbol}` | Yes, needs stored prices |
| Score this company | Score | `POST /api/scores/{symbol}` (uses the selected file's fundamentals when ticked) | Yes |
| Explain the score | Explain | `GET /api/scores/{symbol}/explanation` | Yes (loads it) |

Overview cards add *Run fundamentals* (`POST /api/files/{id}/fundamentals`), *Run technical
analysis* (`POST /api/technical/{symbol}`) and *Open market data*. **Market data and news
fetches never start automatically** because every fetch uses provider quota; those cards
only open the page.

If a prerequisite is missing, the action opens the right page and a note explains what to
do (for example "Choose or upload a file first"). Failures show the server's own code and
message with a plain hint (a 503 says the key belongs in the backend `.env`).

## Run it on Windows

**Prerequisites:** Python 3.11+ and Node.js 20+ (LTS) installed and on `PATH`.

**Easiest — one file, no Docker:** double-click `start_demo.bat` in the project root.
First run installs the Python and Node packages (a few minutes), then opens two server
windows (backend on port 8000, dashboard on 5173) and your browser at
<http://127.0.0.1:5173>. It uses a local SQLite file (`backend\demo.db`), so you do not
need PostgreSQL. Close the two server windows to stop.

> `start_demo.bat` has **not been run on Windows** (the authoring environment is Linux).
> If it misbehaves, use the manual steps below.

**Manual (two terminals):**

```bat
:: Terminal 1 - backend (from the project root)
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set DATABASE_URL=sqlite+pysqlite:///./demo.db
uvicorn app.main:app --host 127.0.0.1 --port 8000

:: Terminal 2 - dashboard
cd frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. To use PostgreSQL instead, start `docker compose up -d`,
skip the `set DATABASE_URL` line, and keep the default `.env` value.

**API keys (optional)** go only in the backend `.env` file at the project root
(`ALPHA_VANTAGE_API_KEY`, `NEWS_API_KEY`). Restart the backend after changing it. The
dashboard never asks for, stores or sends a key; the browser only talks to `/api` on its
own address (Vite proxies it to the backend).

## Demo walkthrough (no API keys needed)

1. **Overview** — Backend status should say "connected". Press *Load the sample company*
   (uploads a small made-up CSV for company AAA and selects it).
2. Press **Analyze a file** — processing runs and shows the columns, detected types and
   standard concepts. On *Process & report*, *Generate report* then *Download .xlsx*.
3. **Fundamentals** (Run fundamentals) — margins, returns, debt ratios, growth; ratios
   without inputs say why.
4. **Check sentiment** — *Use sample headlines*, then *Score these headlines*. Open "Each
   text and the words behind its score" (note "costs rise" counts as positive: a known
   limit of a word list).
5. **Score this company** — fundamentals + sentiment give an overall score; technical and
   risk are listed as unavailable with the reason. Try custom weights.
6. **Explain the score** — What / How / Why, including the arithmetic cross-check.
7. Return to **Overview** to see every saved result at a glance, and the Recent activity
   list in the sidebar.

With keys: **Market data** (fetch AAPL or any symbol) → **Technical** and **Calculate
risk** (optionally with a benchmark such as SPY that you also fetched) → **Score this
company** now uses all four components. For a PDF: upload one in **Files**, then **Analyze
a file**.

The symbol box is shared by market data, technical, sentiment, risk, score and explain.
The score's fundamentals come from the selected file's row for that ticker, so the symbol
should match the file's ticker (the sample uses `AAA`).

## States

Every request shows exactly one of: **idle hint**, **loading** (spinner), **success**,
**empty** (a "nothing here yet" message — a 404 `*_NOT_FOUND` on a load is treated as
empty, not an error), or **error** (server code and message plus a hint; network failure →
"Cannot reach the backend"). Status badges mean "did this step run", never "good or bad",
and the score ring uses one colour for every value on purpose. Charts are dependency-free
SVG; a missing value breaks the line instead of drawing a zero.

## Design notes

- Plain CSS with system font stacks only (no web fonts, no external requests). A serif is
  used for titles and figures, the system sans for the interface. Palette: slate canvas,
  teal-slate sidebar, one lagoon accent, saffron for focus and warnings.
- Keyboard focus is visible, `prefers-reduced-motion` is respected, and sections that
  expand use native `<details>`.
- No router, state library or chart library. State is React state only; nothing is
  stored in the browser (`localStorage` is not used).
- Display-only choices: "Added the most points" / "Cost the most points" lists hide
  entries that round to 0.0 points (the API response is unchanged).
- Symbols are validated in the browser with the same rule as the backend; an invalid
  symbol never reaches the API.

## Tests and what they prove

Results below are from the authoring sandbox on 2026-10-31, run against the final source.

| Check | How to run | Actual result |
|---|---|---|
| Frontend unit tests (formatting, error mapping, chart geometry, API client URLs/bodies/errors, no secrets in source, **navigation, suggested actions, activity list, overview tiles**) | `cd frontend && npm test` | **24 passed, 0 failed** (13 from before + 11 new) |
| Browser test of the whole dashboard (40 steps, headless Chromium, React StrictMode on, 1280 px and 390 px viewports) | `python e2e/make_fixtures.py` then `node e2e/run-e2e.mjs` (needs Playwright + Chromium) | **40 passed, 0 failed**, on two consecutive runs of the final source |
| Planted faults (to show the new steps can fail) | edited and reverted by hand | "Score this company" not starting the score → 1 step failed; risk action ignoring an invalid symbol → 2 failed; disclaimer removed from the pinned header → 2 failed (after tightening that check) |
| Visual review | screenshots in headless Chromium at 1366×860 and 390×800 | Looked at overview, score, explain and mobile views; fixed a stuck "Loading…" tile, clipped chip row, menu buttons visible on desktop, a duplicated disclaimer lead-in and a too-tall pinned header on phones |
| Production-mode bundle | `esbuild --bundle --minify` of `src/main.jsx` | Bundled (about 263 KB). **This is not `npm run build`.** |
| `npm run build` (Vite) | `cd frontend && npm run build` | **Not run** — Vite could not be installed (no network) |
| Backend suite | `cd backend && python -m pytest` | **Not run** — no network to install dependencies. `backend/` is byte-identical to the uploaded Phase 12 ZIP |
| `start_demo.bat` on Windows | double-click | **Not run** |

**Important limits of the browser test.** It runs against `e2e/mock-api.mjs`, a stand-in
for the backend whose response shapes follow `backend/app/schemas/`; the sentiment,
fundamentals, technical, risk, score and explanation payloads in `e2e/fixtures.json` were
produced by running the **real** backend calculation code (`e2e/make_fixtures.py`). It
shows the dashboard handles those shapes and states; it does **not** show the live server
behaves identically. The test bundle used React 19.2.5 (the only React available there);
`package.json` pins React 18 and the code uses no React-19-only features. Chromium only —
Firefox and Safari were not tried.

### Manual checklist against the REAL backend (please do this once)

1. Overview shows "connected". 2. *Load the sample company*; *Analyze a file*; generate and
download the report and open it in Excel. 3. Fundamentals → Run; the last row's net profit
margin should be 13.08%. 4. Sentiment sample → 6/6 texts, mean +0.500. 5. *Score this
company* → overall about 90.0 (fundamentals + sentiment, default weights). 6. *Explain the
score* → the cross-check says "matches". 7. Upload a real PDF → *Analyze a file*. 8. With a
key: fetch a symbol, run Technical, *Calculate risk* and score. 9. Stop the backend and
press Refresh on Overview → "Cannot reach the backend". 10. Narrow the browser window below
900 px: the menu button appears and the sidebar opens as a drawer.

## Known limitations

- Local demo only: no login, no multi-user separation, no HTTPS, not hardened for the
  internet. Do not expose it publicly.
- One selected file and one symbol at a time; no score/result history or comparison, no
  pagination of the files list, no deleting files. "Recent activity" is this session only.
- Results are not live-updated; use the Refresh buttons or re-run the action.
- Market data and news need server-side keys and have never been exercised against the
  live providers (Phases 6 and 8 caveats still apply). Free keys are rate-limited.
- The Excel report does not yet include fundamentals or score data (Phase 3 scope).
- Phase 2 does not recognise a "Total Equity" column (the sample uses "Shareholders
  Equity"); real spreadsheets with that heading lose debt-to-equity. Not changed here.
- Unverified: `npm run build`, `start_demo.bat` on Windows, Firefox/Safari, real phones,
  screen-reader use (labels, roles and focus are present; no accessibility audit).

## Troubleshooting

- **"Cannot reach the backend"** — backend window not running or not on port 8000.
- **Database "not connected"** — use the SQLite route above or start PostgreSQL.
- **503 on Fetch prices / Fetch news** — add the key to `.env`, restart the backend.
- **Score says "No successful … exists"** — that component has not been run for the
  symbol; it is left out and explained, which is normal. Two components are enough.
- **A suggested action only opened a page** — a prerequisite was missing (file, valid
  symbol); read the note above the input area.

## Error handling added in Phase 14

Every page is wrapped in an error boundary (`components/ErrorBoundary.jsx`): if a page crashes while drawing, the rest of the dashboard stays usable and a fixed message with a "Try again" button is shown - never the error text. Requests time out after 30 s (120 s for uploads, downloads, market and news fetches) and show "The backend is taking too long". A database outage (503 `DATABASE_FAILURE`) gets its own hint instead of the missing-API-key hint. No colours or layout were changed. See `SECURITY_TESTING.md`.
