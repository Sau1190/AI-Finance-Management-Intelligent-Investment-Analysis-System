# Security & testing hardening (Phase 14)

Scope: review and harden what already exists. **No new feature, no new endpoint, no
paid service, nothing sent outside the machine, no investment recommendation.** The
Phase 13 experiments and the dashboard design are unchanged.

## What was audited and what was found

Each row was reproduced or read directly in the code before being changed.

| # | Area | Finding (before) | Fix (Phase 14) | Guarded by |
| --- | --- | --- | --- | --- |
| 1 | Spreadsheet export | A cell containing a control character (`\x0b`, `\x01`) raised `IllegalCharacterError` -> bare 500. A cell over 32,767 characters wrote a workbook Excel calls corrupt. Sheet names starting/ending with `'` are rejected by Excel. | `clean_cell_text`: illegal characters become a visible U+FFFD, long text is cut at the Excel limit, the Summary sheet's Warnings count says how many cells were altered; sheet titles cleaned. | `test_hardening_units.py` (export tests) |
| 2 | Export content (formulas) | Checked: `=`, `+`, `-`, `@`, tab-prefixed and `=HYPERLINK(...)` cells are stored as literal text, never formulas. Already correct. | Regression test added so it stays that way. | `test_formula_like_cells_stay_literal_text_never_formulas` |
| 3 | Database failure / rollback | Processing and export committed without rollback or cleanup: a failed commit left the `.xlsx` or the cleaned CSVs orphaned in `storage/exports`. An unexpected error mid-run was a bare 500 and left earlier sheets' CSVs behind. | New `services/db_safety.commit_or_cleanup` (rollback, best-effort cleanup, generic 503 `DATABASE_FAILURE`); unexpected processing/export errors become a `FAILED` result with a generic message. | export/processing failure tests |
| 4 | Error responses | Database errors re-raised by services and any unexpected exception came back as the framework's plain-text 500. | `core/error_handlers.py`: one envelope `{detail:{code,message}}` for HTTP errors, `AppError`, database errors (503) and unexpected errors (500). No paths, SQL or tracebacks reach the client. | `test_error_envelope_*`, `test_hardening_api.py` |
| 5 | Request size | `await file.read()` loaded the whole body before the size check; JSON bodies had no cap. | `RequestSizeLimitMiddleware` (413; upload cap = `MAX_UPLOAD_BYTES` + 64 KB framing, other bodies 2 MB; also catches a lying/missing Content-Length) and `read_upload_limited` (stops reading at the limit). The existing 400 `FILE_TOO_LARGE` answer for a slightly-too-big file is unchanged. | middleware + reader tests |
| 6 | Paths | Export read the cleaned CSV with `removeprefix("exports/")`, so a stored key such as `exports/../x` could leave the exports folder. Other readers already used the file-name part only. | Same confinement everywhere; new `delete_export_artifacts` is confined too. Stored upload names were already random UUIDs. | `test_cleaned_csv_reader_*`, `test_artifact_deleter_*` |
| 7 | Filenames | `<255-char upload name>-export.xlsx` overflowed the `String(255)` column (PostgreSQL rejects, SQLite hides it). The download name was not stripped of quotes/CRLF. | `build_export_filename`, `safe_download_filename`. | filename tests |
| 8 | API keys | The three keys were plain `str` fields, so `print(settings)` would show them. No code path did, and `.env.example`/`.gitignore` were already clean. | `Field(repr=False)`; tests for `repr`, `.env.example` and `.gitignore`. | `test_the_settings_object_hides_api_keys_from_repr` |
| 9 | Logs | `logger.exception(...)` in the processing/export/PDF/fundamentals paths wrote the exception text and chain (which parsers can fill with cell content) into the log. | Those calls now log only the error type or code. An AST test fails if any logging call prints an exception object or `str(exc)`, and restricts `logger.exception` to the storage-cleanup helpers. | the two logging tests |
| 10 | HTTP surface | CORS allowed credentials plus wildcard methods/headers though no cookies exist; no `nosniff`/`no-store` headers. | CORS: no credentials, `GET/POST/OPTIONS`, `Content-Type`/`Accept`, a `*` origin is ignored. Security headers on every response (not on `/docs`). | header tests |
| 11 | Frontend | A render error blanked the whole page; no fetch timeout (a hung backend = endless spinner); a 200 answer with a non-JSON body surfaced a parser error; a 503 database failure got the "add an API key" hint. | `ErrorBoundary` (fixed generic text, logs only the error type) around the app and every page; 30 s timeout (120 s for uploads, downloads, market and news fetches); readable `INVALID_RESPONSE`; database/internal-error hints. | `frontend/tests/hardening.test.js` |
| 12 | Frontend secrets | Checked: no keys, `localStorage`/`sessionStorage`/cookies, `dangerouslySetInnerHTML`, or third-party links in the source. | A test scans the whole `src/` tree so it stays true. | last test in `hardening.test.js` |

Already fine and left alone: provider adapters never log or return a key; symbol/query/
weights validation; the zip-bomb guard on XLSX uploads; upload names are random UUIDs.

## Checks actually run (2026-11-01, build sandbox)

| Check | Result |
| --- | --- |
| New backend hardening tests, `tests/test_hardening_units.py` (real service code, fake DB session, plain ASGI apps) | **32 passed**, run with sandbox-only stubs for `pydantic-settings`/`sqlalchemy` (see below) |
| Planted faults against those tests (27 breakages: export, processing, DB safety, readers, middleware, headers, config, logging, env) | **27 of 27 caught** (one escaped first - filename truncation at service level - a test was added; then all caught) |
| ML experiment tests (`python -m unittest discover -s ml_experiments/tests -t .`) | **18 passed** |
| Frontend unit tests (`npm test`) | **33 passed** (24 existing + 9 new); 7 planted faults caught |
| Browser test (headless Chromium, **mock API only**) | 40/40 on each of the 4 later runs of the final source; the very first run reported 39/40 with one step failing that I did not identify and could not reproduce in later runs (the unmodified Phase 13 source passed 3/3). Treat that step as possibly timing-sensitive. |
| Error boundary in a real browser (bundled component, deliberately crashing child) | Crash screen shown, shell stays, no error text on screen, console line carries only `TypeError`, "Try again" recovers |
| Frontend production bundle (esbuild, minified) | Built (265 KB). This is **not** `npm run build`. |

## Checks NOT run - please run them

* **`python -m pytest` in `backend/`** (the full suite incl. the new `tests/test_hardening_api.py`). FastAPI/SQLAlchemy/pydantic-settings could not be installed (no network), so the 13 API test modules, the new `test_hardening_api.py` (7 tests), `app/main.py`, `core/error_handlers.py` and the route edits in `routes/files.py`/`routes/export.py` were only syntax-checked here, **never executed**. They are the most likely place for a first failure; `test_hardening_api.py` was written against the existing `client` fixture without being run.
* **`npm run build` (Vite)**, `start_demo.bat` on Windows, anything against the real backend, a real PostgreSQL outage, a live provider, Firefox/Safari.

Sandbox-only stubs (`pydantic-settings`, `sqlalchemy`) were used to run `test_hardening_units.py`; they are not in the ZIP. With the real packages that file needs nothing else (it works with the suite's `conftest.py` as well).

## Remaining limitations (not fixed, by design or scope)

* **No authentication or rate limiting.** Anyone who can reach port 8000 can use the API, upload files and spend your provider quota. It is built for one person on one computer: keep `API_HOST=127.0.0.1`, do not port-forward or deploy it as is. Authentication belongs to the deployment phase.
* A completely unexpected (500) error is answered by Starlette's outermost error layer, so that one response carries no CORS header and the browser may report it as "cannot connect" instead of the friendly message when the dashboard is not served through the Vite proxy.
* Uploaded PDFs and workbooks are still parsed by third-party libraries (PyMuPDF, openpyxl, pandas) in the API process; a malicious file that triggers a parser bug is not sandboxed. Size, zip-bomb and row limits apply.
* Dependency versions are pinned but were not scanned for known vulnerabilities (no network); run `pip-audit` / `npm audit` yourself.
* A Content-Security-Policy for the dashboard is not set (it would be a deployment-time header on whatever serves the built files).
* Market/news provider calls were never made live (earlier phases); their error handling is tested against simulated transports only.
