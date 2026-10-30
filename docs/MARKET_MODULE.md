# Market data module (Phase 6 — verified complete, 2026-10-13)

Fetches daily price history for a ticker symbol from an external provider,
validates it, stores it, and records an explainable snapshot. It is the data
layer only: no technical indicators (Phase 7), no sentiment (Phase 8), no
scoring, no LLM, and nothing is linked to uploaded files yet.

> **Live provider calls are untested.** The build environment has no outbound
> access to the provider (DNS does not resolve), so the Alpha Vantage adapter
> was verified only against a simulated transport that returns the vendor's
> documented response shape. Before relying on it, run one real fetch with your
> own key and compare the stored bars with the provider's website.

## Design

- **Adapter pattern.** `MarketDataProvider.fetch_daily(symbol, history)` is the whole contract. `AlphaVantageProvider` implements it (`TIME_SERIES_DAILY`, JSON). Adapters only fetch and reshape — they never validate, repair, or invent prices.
- **Shared validation** (`market_validation.py`) is provider-independent, so a future provider is held to the same rules.
- **Configuration.** `MARKET_DATA_PROVIDER` (default `alpha_vantage`), `ALPHA_VANTAGE_API_KEY`, `MARKET_DATA_TIMEOUT_SECONDS` (default 10), `MARKET_DIR` (default `backend/storage/market`). The key lives only in the server environment/`.env` (git-ignored); it is never in source, responses, the database, stored files, or logs.

## Validation rules (a bar is accepted exactly as received or rejected — never repaired)

Rejected, with a counted reason in `rejected_bars`: invalid date (must be `YYYY-MM-DD`), future date (more than 1 day ahead of UTC today — exchange-local dates can lead UTC), non-numeric or non-finite open/high/low/close, non-positive prices, volume that is negative / non-integer / non-numeric, high below low, open or close outside the high–low range, and **duplicate dates (both bars dropped — we cannot know which is right)**. Accepted bars are sorted ascending and use native types.

If some bars are rejected the snapshot is still `COMPLETE` and says how many and why. If **no** valid bar remains it is `FAILED` (`NO_VALID_BARS`).

Not modelled: splits and dividends. `TIME_SERIES_DAILY` is as-traded (unadjusted), so a split appears as a price jump.

## API

- `POST /api/market-data/{symbol}?history=compact|full` — fetch and store. 201 in every fetch outcome; a provider problem is `status: FAILED` with an `error_code`. 400 `INVALID_SYMBOL`; 422 for a bad `history`; **503 `MARKET_DATA_NOT_CONFIGURED`** if no key/provider is configured (nothing is recorded; this check runs before input validation).
- `GET /api/market-data/{symbol}` — the latest fetch attempt (successful or not); 404 `MARKET_RESULT_NOT_FOUND`.
- `GET /api/market-data/{symbol}/prices?limit=1..1000` (default 100) — the most recent bars, ascending by date, from the latest **successful** fetch (a later failed fetch does not hide good data); 404 `PRICES_NOT_FOUND` or `MARKET_DATA_UNAVAILABLE` (stored file gone).

Symbols: 1–10 characters, letters/digits/`.`/`-`, first character alphanumeric; stored upper-case. Anything else is rejected before any provider call.

Error codes on a `FAILED` snapshot: `PROVIDER_REJECTED_REQUEST` (unknown symbol *or* invalid key — the vendor does not distinguish them), `PROVIDER_DECLINED_REQUEST` (rate limit / quota / plan), `PROVIDER_TIMEOUT`, `PROVIDER_UNREACHABLE`, `PROVIDER_HTTP_ERROR`, `PROVIDER_BAD_RESPONSE`, `PROVIDER_NO_DATA`, `NO_VALID_BARS`, `MARKET_STORAGE_FAILURE`, `MARKET_DATA_FAILURE`. Messages are authored by this project; raw vendor text is never echoed.

## Security notes

- **The API key is in the request URL** (the vendor requires a query parameter). So: adapter errors are mapped to fixed messages with the original exception suppressed (`from None`); the service logs only an error code or exception *type*; **`httpx`/`httpcore` loggers are pinned to WARNING** because `httpx` otherwise logs the full URL, key included, at INFO (found and fixed during verification); redirects are not followed, so the key cannot be forwarded to another host; response size is capped at 10 MB; requests have a timeout.
- Symbols are validated before use, and stored-file access uses only the file-name part of a key.
- Tests never use a real key: `conftest.py` blanks `ALPHA_VANTAGE_API_KEY`.

## Storage and completeness

One CSV per successful fetch in `storage/market/` (generated names, exclusive creation, never overwrites, part-written file removes itself). A `COMPLETE` snapshot always has its file. A storage failure makes the fetch `FAILED`; if the database row cannot be saved, the file is deleted and the error propagates.

## Operational notes

- Free Alpha Vantage keys allow only a handful of requests per minute and ~25 per day. Every `POST` calls the provider (no caching), so repeated calls consume quota; a refusal appears as `PROVIDER_DECLINED_REQUEST`.
- `full` history can be large (decades of bars); it is stored as a CSV, only a 5-bar preview is kept in the database.

## Tests

`backend/tests/test_market_data.py` (81 tests, no network): adapter request shape and every failure mapping (including redirects, oversize, malformed rows, missing key); key never present in errors, responses, database rows, stored files, or logs at DEBUG; 17 bar-rejection cases and duplicates/tolerance/zero-volume; successful fetch, preview, history option, partial rejection, price ordering/limits; invalid and path-like symbols; unconfigured/unsupported provider; provider failures recorded without fabricating data and without hiding earlier good data; storage, partial-write and database-failure cleanup; deleter safety.

## Known limitations

- Single provider and daily bars only (no intraday, quotes, fundamentals, or news).
- Not yet connected to uploaded files or Phase 5 (the `ticker` column is not used to fetch anything).
- No response caching, scheduling, or retry/back-off.
- Prices are unadjusted for splits/dividends.
- Prices are not downloadable as a file through the API (JSON endpoint only).
