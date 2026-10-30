"""Deterministic technical indicators over daily price bars.

Beginner view:
  Indicators are numbers worked out from past prices — for example a 20-day
  average. This module computes them and says exactly how. It never says
  "buy", "sell", "overbought" or "bullish": reading what the numbers mean is
  the job of the later scoring/explanation phases.

Technical view:
  Pure functions over lists of floats (no pandas, no I/O). Inputs are bars
  already validated by Phase 6: ascending dates, finite positive prices. The
  definitions below are the common textbook ones; every choice that can differ
  between charting packages is stated here so results are reproducible:

    SMA(n)        mean of the last n closes.
    EMA(n)        alpha = 2/(n+1). Seeded with the SMA of the first n values
                  (not with the first value), then
                  EMA_t = alpha*x_t + (1-alpha)*EMA_{t-1}.
    MACD          line = EMA(12) - EMA(26); signal = EMA(9) of the MACD line
                  (seeded with the SMA of its first 9 values);
                  histogram = line - signal.
    RSI(n)        Wilder. First average gain/loss = simple mean of the first n
                  price changes; afterwards avg = (prev*(n-1) + current)/n.
                  RSI = 100 - 100/(1 + avg_gain/avg_loss). avg_loss == 0 with
                  gains -> 100. avg_gain == avg_loss == 0 (no movement in the
                  smoothed window) -> undefined (None), never a made-up 50.
    Bollinger     middle = SMA(n); bands = middle +/- k * population standard
                  deviation (divide by n, not n-1) of the same n closes.
    ATR(n)        Wilder. TR_t = max(high-low, |high-prev_close|,
                  |low-prev_close|) for t >= 1 (the first bar has no previous
                  close, so no TR). First ATR = mean of TR_1..TR_n; afterwards
                  ATR = (prev*(n-1) + TR)/n.

  Every function returns a list the same length as its input, with None for
  rows that lack enough history ("warm-up") or are undefined. Values are
  native Python floats.
"""

import math

Series = list[float | None]


def sma(values: list[float], period: int) -> Series:
    out: Series = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = sum(values[i - period + 1 : i + 1]) / period
    return out


def ema(values: Series, period: int) -> Series:
    """EMA seeded with the SMA of the first `period` values. `values` may begin
    with None (e.g. a MACD line during warm-up); the seed window starts at the
    first non-None value and must be contiguous after that.
    """
    n = len(values)
    out: Series = [None] * n
    first = next((i for i, v in enumerate(values) if v is not None), None)
    if first is None:
        return out
    seed_end = first + period - 1
    if seed_end >= n:
        return out
    window = values[first : seed_end + 1]
    if any(v is None for v in window):
        return out
    alpha = 2.0 / (period + 1)
    out[seed_end] = sum(window) / period  # type: ignore[arg-type]
    for i in range(seed_end + 1, n):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]  # type: ignore[operator]
    return out


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, Series]:
    fast_ema = ema(list(values), fast)
    slow_ema = ema(list(values), slow)
    line: Series = [
        (f - s) if f is not None and s is not None else None for f, s in zip(fast_ema, slow_ema)
    ]
    signal_line = ema(line, signal)
    histogram: Series = [
        (m - s) if m is not None and s is not None else None for m, s in zip(line, signal_line)
    ]
    return {"macd": line, "macd_signal": signal_line, "macd_histogram": histogram}


def rsi(values: list[float], period: int = 14) -> Series:
    n = len(values)
    out: Series = [None] * n
    if n < period + 1:
        return out
    gains = [max(values[i] - values[i - 1], 0.0) for i in range(1, n)]
    losses = [max(values[i - 1] - values[i], 0.0) for i in range(1, n)]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def value(gain: float, loss: float) -> float | None:
        if loss == 0:
            return None if gain == 0 else 100.0
        return 100.0 - 100.0 / (1.0 + gain / loss)

    out[period] = value(avg_gain, avg_loss)
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = value(avg_gain, avg_loss)
    return out


def bollinger(values: list[float], period: int = 20, k: float = 2.0) -> dict[str, Series]:
    n = len(values)
    middle: Series = [None] * n
    upper: Series = [None] * n
    lower: Series = [None] * n
    for i in range(period - 1, n):
        window = values[i - period + 1 : i + 1]
        mean = sum(window) / period
        deviation = math.sqrt(sum((x - mean) ** 2 for x in window) / period)
        middle[i] = mean
        upper[i] = mean + k * deviation
        lower[i] = mean - k * deviation
    return {"bb_middle": middle, "bb_upper": upper, "bb_lower": lower}


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> Series:
    n = len(closes)
    out: Series = [None] * n
    if n < period + 1:
        return out
    true_range = [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        for i in range(1, n)
    ]  # true_range[j] belongs to bar j+1
    current = sum(true_range[:period]) / period
    out[period] = current
    for i in range(period + 1, n):
        current = (current * (period - 1) + true_range[i - 1]) / period
        out[i] = current
    return out
