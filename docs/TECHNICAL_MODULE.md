# Technical analysis module (Phase 7 — verified complete, 2026-10-13)

Computes standard technical indicators from a symbol's stored daily prices
(Phase 6). It states **what** each value is and **how** it was computed. It
never says "buy", "sell", "overbought", "bullish" or similar — interpreting the
numbers belongs to the later scoring/explanation phases. No LLM, no new
dependency, no network access.

## Pipeline

1. Market data must exist: `POST /api/market-data/{symbol}` (Phase 6)
2. `POST /api/technical/{symbol}` takes the symbol's latest **successful** market snapshot (a newer failed fetch does not hide good data)
3. Bars are read from the stored Phase 6 file (read-only), indicators are computed, and the full per-bar series is written to `backend/storage/analysis/` (shared with Phase 5's metric files; same storage rules)
4. A `TechnicalAnalysisResult` records the indicator report and the `market_snapshot_id` it was computed from, so it stays explainable after newer prices arrive

## Indicators (13 series)

| Series | Definition | Bars needed |
| --- | --- | --- |
| `sma_20`, `sma_50`, `sma_200` | mean of the last n closes | n |
| `ema_12`, `ema_26` | alpha = 2/(n+1); **seeded with the SMA of the first n closes** | n |
| `macd` | EMA(12) − EMA(26) | 26 |
| `macd_signal` | EMA(9) of the MACD line (SMA-seeded) | 34 |
| `macd_histogram` | MACD − signal | 34 |
| `rsi_14` | Wilder: first averages = simple mean of the first 14 changes, then avg = (prev×13 + current)/14; 100 − 100/(1 + avg gain/avg loss) | 15 |
| `bb_middle`, `bb_upper`, `bb_lower` | SMA(20) ± 2 × **population** standard deviation (÷ n) | 20 |
| `atr_14` | Wilder smoothing of true range = max(high−low, \|high−prev close\|, \|low−prev close\|); first ATR = mean of TR₁..TR₁₄ | 15 |

These are the common textbook choices. Charting packages differ on EMA seeding, Wilder vs. plain smoothing, and sample vs. population deviation, so values can differ slightly from other tools — the choices above are fixed and documented so results are reproducible.

## Honesty rules

- **No padding or approximation.** A series that lacks enough bars is `NOT_COMPUTABLE` with the reason (`Needs at least 200 bars; 60 available.`) and is left out of the CSV; it is never computed from a shorter window. **Phase 6's default `compact` history is only ~100 bars, so `sma_200` needs `?history=full`.**
- **Warm-up rows are null**, reported as `warmup_rows` (= bars needed − 1).
- **Undefined is not invented.** RSI is undefined (null, counted in `undefined_rows`) when the smoothed gain and loss are both 0 (no price movement); it is never filled with 50. RSI is exactly 100 when there are gains and no losses, 0 with losses and no gains.
- Fewer than 12 bars (the smallest requirement) is a `FAILED` run with `INSUFFICIENT_DATA` and no artifact.
- Values are native Python floats; nothing is rounded in storage.

## Result shape

`TechnicalAnalysisResultResponse`: `id`, `symbol`, `market_snapshot_id`, `status` (`COMPLETE` | `FAILED`), `created_at`, `error_code`, `error_message`, `bar_count`, `first_date`, `last_date`, `indicators[]`, `preview_rows` (last 5 rows), `indicators_storage_key`.

Each indicator: `key`, `label`, `description`, `parameters`, `min_bars`, `status` (`COMPUTED` | `NOT_COMPUTABLE`), `reason`, `warmup_rows`, `computed_count`, `undefined_rows`, `min`, `max`, `latest`, `latest_date`.

## API

- `POST /api/technical/{symbol}` — 201 in every run outcome (a failed run has `status: FAILED` and an error code). 400 `INVALID_SYMBOL`; 404 `MARKET_DATA_NOT_FOUND` (no successful market fetch yet).
- `GET /api/technical/{symbol}` — latest run, successful or not; 404 `TECHNICAL_RESULT_NOT_FOUND`.
- `GET /api/technical/{symbol}/series?limit=1..1000` (default 100) — most recent rows (ascending by date), one value per indicator, `null` where there is no value; from the latest **successful** run; 404 `TECHNICAL_SERIES_NOT_FOUND` / `TECHNICAL_DATA_UNAVAILABLE`.

Failed-run codes: `INSUFFICIENT_DATA`, `MARKET_DATA_UNAVAILABLE` (stored prices gone), `TECHNICAL_ANALYSIS_FAILURE` (unexpected error; only the exception type is logged), `ANALYSIS_STORAGE_FAILURE`.

## Completeness and storage failures

A `COMPLETE` result always has its series file. A storage failure or unexpected error makes the run `FAILED` and keeps nothing; a part-written file removes itself; if the result row cannot be saved, its file is deleted and the error propagates.

## Verification of the maths

Three independent kinds of evidence, not just self-consistency: (1) hand-computed values for small inputs (SMA, EMA, ATR incl. a price gap); (2) **pandas** as an independent implementation for SMA and Bollinger (population std); (3) a **published external reference series** for RSI(14) — the six published values 70.53, 66.32, 66.55, 69.41, 66.36, 57.97 are reproduced exactly (to two decimals) from the reference closes. (With the closes rounded to 2 decimals the values differ by ~0.07 — a property of the data, not the code.) Mutation checks confirmed the tests fail if Wilder smoothing, population deviation, previous-close true range, SMA seeding, or the minimum-bars rule is changed.

## Tests

`backend/tests/test_technical.py` (43 tests, no network): indicator maths (above); report builder (full, short, minimum, undefined-vs-warm-up); API computation matches independent calculations; traceability to the market snapshot; newer failed fetch ignored; no trading-judgement vocabulary in results; Phase 6 data never modified; series endpoint (ordering, nulls, limits, 422, failed-run fallback, missing file); 404/400 cases; unavailable market file, unexpected error without leakage, storage failure, partial write, database failure.

## Known limitations

- Only the indicators above, with fixed standard parameters (not configurable); no volume indicators, no intraday data.
- Uses unadjusted prices (Phase 6): a stock split appears as a price jump and distorts every indicator across it.
- Not yet used by anything downstream; no signals, scores, or explanations (Phases 10–11).
- Output is available as JSON (preview and `/series`) but not as a downloadable file or in the Excel export.
- Live market data has never been fetched (see `MARKET_MODULE.md`); indicators were verified on stored test bars.
