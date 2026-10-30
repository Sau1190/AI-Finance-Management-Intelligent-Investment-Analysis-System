# Risk module (Phase 9 — verified complete, 2026-10-27)

Computes **market-risk metrics from a symbol's stored daily prices** (Phase 6),
optionally measured against a benchmark symbol. It states **what** each number
is and **how** it was computed. It describes the past only: it never says a
stock is "high risk", "low risk", "safe", or "risky" — that judgement belongs to
the scoring phase (Phase 10). No LLM, no new dependency, no network access.

Scope: price-based market risk. Leverage/solvency risk from financial
statements is already covered by Phase 5's ratios (e.g. `debt_to_equity`);
combining everything into one assessment is Phase 10.

## Pipeline

1. Market data must exist: `POST /api/market-data/{symbol}` (Phase 6) — for the symbol and, if used, the benchmark
2. `POST /api/risk/{symbol}?benchmark=SPY` takes each symbol's latest **successful** snapshot (a newer failed fetch does not hide good data)
3. Bars are read from the stored Phase 6 files (read-only) and metrics are computed
4. A `RiskAnalysisResult` records the metrics, warnings, and the `market_snapshot_id` / `benchmark_snapshot_id` it used, so it stays explainable after newer prices are fetched. Results are stored inline (no file artifacts).

## Metrics (10)

All use simple close-to-close daily returns `r = close_t / close_{t-1} − 1`.

| Key | Definition | Needs |
| --- | --- | --- |
| `daily_volatility` | **sample** standard deviation (n−1) of daily returns | 20 returns |
| `annualized_volatility` | daily × √252 (252 trading days/year is a convention, reported in `parameters`) | 20 returns |
| `max_drawdown` | largest peak-to-trough fall of the close, `close / running peak − 1` (negative); details: peak, trough and recovery dates (recovery = first later close ≥ the peak, else `null`), bars to trough/recovery | 1 return |
| `current_drawdown` | latest close / highest close in the window − 1 (0 at a new high); details: date of the most recent high | 1 return |
| `worst_day`, `best_day` | lowest / highest single-day return, with its date | 1 return |
| `historical_var_95` | 5th percentile of daily returns, linear interpolation between order statistics. **−0.021 means "on about 5% of days the return was −2.1% or worse"** | 100 returns |
| `historical_cvar_95` | mean of all returns ≤ the VaR value | 100 returns |
| `beta` | cov(asset, benchmark) / var(benchmark) | 60 aligned returns |
| `correlation` | Pearson correlation of the same returns | 60 aligned returns |

**Benchmark alignment.** Only dates present in *both* series are used, and each return spans consecutive *common* dates, so asset and benchmark returns always cover the same holding period even when one series is missing days. `details.aligned_returns` reports how many were used.

**Not computed on purpose:** Sharpe, Sortino, alpha (they need a risk-free-rate assumption this project does not hardcode), skew/kurtosis, parametric VaR.

## Honesty rules

- **No approximation.** A metric without enough history is `NOT_COMPUTABLE` with the reason (`Needs at least 100 daily returns; 59 available.`), never computed from a shorter window. The floors (20 / 100 / 60) are **reliability floors chosen by judgement, not statistical standards** — they are reported, and fewer returns than they imply give very noisy estimates. Historical VaR from ~100 returns rests on only ~5 tail observations.
- **Undefined stays undefined.** A zero-variance benchmark or asset leaves beta/correlation `NOT_COMPUTABLE` with the reason, never a made-up number.
- **Split warning, not split repair.** Prices are **as-traded (unadjusted)**, so a stock split looks like a one-day crash and distorts volatility, drawdown, VaR, and beta. The data cannot tell a real crash from a split, so nothing is repaired; instead, if any single day moves more than **30%** (a heuristic, not a standard), `warnings` says how many such moves there were, the largest and its date, and that the metrics may be overstated. The benchmark is checked the same way under its own name.
- A result with warnings is still `COMPLETE`; the metrics are computed from the data exactly as stored.
- Values are native Python floats; nothing is rounded in storage.

## Result shape

`RiskAnalysisResultResponse`: `id`, `symbol`, `benchmark_symbol`, `market_snapshot_id`, `benchmark_snapshot_id`, `status` (`COMPLETE` | `FAILED`), `created_at`, `error_code`, `error_message`, `bar_count`, `returns_count`, `first_date`, `last_date`, `metrics[]`, `warnings[]`.

Each metric: `key`, `label`, `description`, `parameters`, `min_returns`, `status` (`COMPUTED` | `NOT_COMPUTABLE`), `reason`, `value`, `details`.

## API

- `POST /api/risk/{symbol}?benchmark=SYMBOL` — 201 in every run outcome (a failed run has `status: FAILED` and an error code). 400 `INVALID_SYMBOL` (symbol or benchmark); 400 `INVALID_BENCHMARK` (same as the symbol, case-insensitive); 404 `MARKET_DATA_NOT_FOUND` / `BENCHMARK_DATA_NOT_FOUND` (no successful market fetch yet).
- `GET /api/risk/{symbol}` — latest run, successful or not; 404 `RISK_RESULT_NOT_FOUND`.

Failed-run codes: `INSUFFICIENT_DATA` (fewer than 2 bars), `MARKET_DATA_UNAVAILABLE` (a stored price file is gone), `RISK_ANALYSIS_FAILURE` (unexpected error; only the exception type is logged, nothing leaks).

## Verification of the maths

Three independent kinds of evidence: (1) hand-computed values for small inputs (returns, sample std, drawdown with and without recovery, quantile interpolation, VaR/CVaR, benchmark alignment across a missing day); (2) **pandas/numpy** as independent implementations on random data — volatility, drawdown and trough date, VaR, CVaR, worst day, beta, correlation and the aligned-return count agreed to 9 decimals through the live API; (3) mathematical properties (a series has beta 1 and correlation 1 against itself, 2× the returns has beta 2, the negative has beta −1, CVaR ≤ VaR). Ten mutations (population instead of sample std, 365-day annualization, no quantile interpolation, strict-greater recovery, lowered VaR floor, inverted beta, CVaR tail excluding the VaR point, a raised split threshold, benchmark equal to the symbol, first instead of latest high) were each caught.

**Finding during verification:** `1.0 − 0.95` is `0.050000000000000044` in floating point, which put the VaR percentile position at 1.0000000000000009 instead of exactly 1.0 and let a CVaR tail-boundary mutation slip past the hand-computed test. The tail probability is now rounded so tie behaviour is deterministic, and that mutation is now caught directly.

## Tests

`backend/tests/test_risk.py` (58 tests, no network): hand-computed maths; pandas/numpy cross-checks and properties; report builder (full, short history, exact minimum-history boundaries, two-bar minimum, flat series, constant benchmark, no risk-judgement vocabulary, native types); split-like moves flagged but not repaired (asset and benchmark, crash-and-rebound); API with and without a benchmark, snapshot traceability, benchmark with missing days, newer failed fetch ignored, Phase 6 files unmodified, per-symbol results; 404/400 cases; single bar, missing stored files, unexpected error without leakage, database failure.

## Known limitations

- Prices are unadjusted for splits and dividends (see the warning above); returns exclude dividends.
- Daily close-to-close returns only; a short or recent history gives noisy estimates, and a window dominated by one regime says little about another.
- Historical VaR/CVaR assume the past distribution of daily returns describes the future; they say nothing about losses beyond the window.
- Beta depends entirely on the benchmark you choose and the overlapping window; a poorly matched benchmark gives a meaningless beta.
- Not linked to fundamentals (Phase 5), sentiment (Phase 8), or uploaded files; no portfolio-level risk.
- Live market data has never been fetched (see `MARKET_MODULE.md`); metrics were verified on stored test bars.
