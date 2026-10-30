"""Deterministic market-risk metrics from daily closing prices.

Beginner view:
  Risk metrics describe how bumpy and how painful a price history has been:
  how much it swings day to day (volatility), the worst fall from a peak
  (drawdown), how bad a typical "bad day" was (VaR), and how closely it moves
  with the overall market (beta). They describe the PAST only and say nothing
  about whether a stock is "safe" or "risky" — that judgement is the scoring
  phase's job, not this module's.

Technical view:
  Pure functions (no pandas, no I/O) over lists of ascending-date closes
  validated by Phase 6. Definitions, with every choice that can differ between
  tools stated so results are reproducible:

    return          simple daily return r_t = close_t / close_{t-1} - 1
                    (close-to-close; prices are as-traded, NOT adjusted for
                    splits/dividends).
    volatility      SAMPLE standard deviation (n-1) of daily returns;
                    annualized = daily * sqrt(252) (252 trading days/year is
                    a convention, reported in the output, not a measurement).
    max drawdown    the largest peak-to-trough fall of the close series,
                    close/running_peak - 1 (a negative number). The recovery
                    date is the first later date whose close is >= that peak,
                    or None if it never recovered.
    current drawdown  latest close / highest close in the window - 1.
    historical VaR(95)  the 5th percentile of daily returns, by linear
                    interpolation between order statistics (position
                    (n-1)*0.05 in the sorted returns). A value of -0.021 means
                    "on about 5% of days the return was -2.1% or worse".
    historical CVaR(95)  the mean of all returns <= the VaR value.
    beta            cov(asset, benchmark) / var(benchmark) of returns computed
                    between consecutive COMMON dates of the two series (so both
                    returns cover the same holding period even when one series
                    is missing a day); correlation is Pearson on the same
                    returns.

  Not computed on purpose: Sharpe/Sortino/alpha (they need a risk-free-rate
  assumption this project does not hardcode).

  Values are native Python floats. Sample sizes are small enough that these are
  rough estimates; the minimum-history floors below are reliability floors and
  are reported, not hidden.
"""

import math

TRADING_DAYS_PER_YEAR = 252
VAR_LEVEL = 0.95
LARGE_MOVE_THRESHOLD = 0.30

MIN_RETURNS_VOLATILITY = 20
MIN_RETURNS_VAR = 100
MIN_ALIGNED_RETURNS_BETA = 60


def simple_returns(closes: list[float]) -> list[float]:
    return [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def sample_std(values: list[float]) -> float:
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def quantile(values: list[float], q: float) -> float:
    """Linear-interpolation quantile (the common 'type 7' definition)."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def max_drawdown(dates: list[str], closes: list[float]) -> dict:
    peak_index = 0
    worst = 0.0
    worst_peak = worst_trough = 0
    for i, close in enumerate(closes):
        if close > closes[peak_index]:
            peak_index = i
        drawdown = close / closes[peak_index] - 1.0
        if drawdown < worst:
            worst, worst_peak, worst_trough = drawdown, peak_index, i
    recovery = next(
        (i for i in range(worst_trough + 1, len(closes)) if closes[i] >= closes[worst_peak]), None
    ) if worst < 0 else None
    return {
        "value": worst,
        "peak_date": dates[worst_peak] if worst < 0 else None,
        "trough_date": dates[worst_trough] if worst < 0 else None,
        "recovery_date": dates[recovery] if recovery is not None else None,
        "bars_peak_to_trough": (worst_trough - worst_peak) if worst < 0 else 0,
        "bars_to_recovery": (recovery - worst_trough) if recovery is not None else None,
    }


def current_drawdown(dates: list[str], closes: list[float]) -> dict:
    peak = max(closes)
    peak_index = max(i for i, c in enumerate(closes) if c == peak)  # most recent high
    return {
        "value": closes[-1] / peak - 1.0,
        "peak_date": dates[peak_index],
        "peak_close": peak,
        "latest_date": dates[-1],
        "latest_close": closes[-1],
    }


def historical_var_cvar(returns: list[float], level: float = VAR_LEVEL) -> tuple[float, float]:
    # 1.0 - 0.95 is 0.050000000000000044 in floating point; round so the percentile
    # position is exactly (n-1)*0.05 and ties at an order statistic behave deterministically.
    var = quantile(returns, round(1.0 - level, 12))
    tail = [r for r in returns if r <= var]
    return var, mean(tail)


def align_on_common_dates(
    asset: list[dict], benchmark: list[dict]
) -> tuple[list[str], list[float], list[float]]:
    bench_close = {bar["date"]: bar["close"] for bar in benchmark}
    dates = [bar["date"] for bar in asset if bar["date"] in bench_close]
    asset_close = {bar["date"]: bar["close"] for bar in asset}
    return dates, [asset_close[d] for d in dates], [bench_close[d] for d in dates]


def beta_correlation(asset_returns: list[float], bench_returns: list[float]) -> tuple[float | None, float | None]:
    ma, mb = mean(asset_returns), mean(bench_returns)
    n = len(asset_returns)
    cov = sum((a - ma) * (b - mb) for a, b in zip(asset_returns, bench_returns)) / (n - 1)
    var_b = sum((b - mb) ** 2 for b in bench_returns) / (n - 1)
    var_a = sum((a - ma) ** 2 for a in asset_returns) / (n - 1)
    beta = cov / var_b if var_b > 0 else None
    correlation = cov / math.sqrt(var_a * var_b) if var_a > 0 and var_b > 0 else None
    return beta, correlation
