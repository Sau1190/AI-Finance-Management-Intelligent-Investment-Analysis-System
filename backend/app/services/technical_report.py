"""Turns price bars into an explainable technical-indicator report.

Pure (no database, no storage). For each indicator series it states the
definition, its parameters, how many bars it needs, how many leading rows are
warm-up, how many rows are undefined, and summary values. A series that lacks
enough history is NOT_COMPUTABLE with the reason — it is never padded,
extrapolated, or approximated with a shorter window.
"""

import csv
import io
from dataclasses import dataclass

from app.services import technical_indicators as ti

PREVIEW_ROWS = 5


@dataclass(frozen=True)
class SeriesSpec:
    key: str
    label: str
    description: str
    parameters: dict
    min_bars: int


def _sma(n: int) -> SeriesSpec:
    return SeriesSpec(f"sma_{n}", f"Simple moving average ({n})", "Mean of the last n closes.", {"period": n}, n)


def _ema(n: int) -> SeriesSpec:
    return SeriesSpec(
        f"ema_{n}",
        f"Exponential moving average ({n})",
        "alpha = 2/(n+1); seeded with the SMA of the first n closes.",
        {"period": n},
        n,
    )


_MACD_PARAMS = {"fast": 12, "slow": 26, "signal": 9}

SERIES_SPECS: tuple[SeriesSpec, ...] = (
    _sma(20),
    _sma(50),
    _sma(200),
    _ema(12),
    _ema(26),
    SeriesSpec("macd", "MACD line", "EMA(12) - EMA(26) of the close.", _MACD_PARAMS, 26),
    SeriesSpec("macd_signal", "MACD signal", "EMA(9) of the MACD line (SMA-seeded).", _MACD_PARAMS, 34),
    SeriesSpec("macd_histogram", "MACD histogram", "MACD line - MACD signal.", _MACD_PARAMS, 34),
    SeriesSpec(
        "rsi_14",
        "Relative strength index (14)",
        "Wilder smoothing; 100 - 100/(1 + avg gain/avg loss). Undefined when the smoothed gain and loss are both 0.",
        {"period": 14},
        15,
    ),
    SeriesSpec("bb_middle", "Bollinger middle band (20)", "SMA(20) of the close.", {"period": 20, "k": 2.0}, 20),
    SeriesSpec(
        "bb_upper", "Bollinger upper band (20, 2)", "Middle + 2 x population standard deviation.", {"period": 20, "k": 2.0}, 20
    ),
    SeriesSpec(
        "bb_lower", "Bollinger lower band (20, 2)", "Middle - 2 x population standard deviation.", {"period": 20, "k": 2.0}, 20
    ),
    SeriesSpec(
        "atr_14",
        "Average true range (14)",
        "Wilder smoothing of true range = max(high-low, |high-prev close|, |low-prev close|).",
        {"period": 14},
        15,
    ),
)

MIN_BARS_FOR_ANY = min(spec.min_bars for spec in SERIES_SPECS)


def _compute_series(bars: list[dict]) -> dict[str, ti.Series]:
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    series: dict[str, ti.Series] = {
        "sma_20": ti.sma(closes, 20),
        "sma_50": ti.sma(closes, 50),
        "sma_200": ti.sma(closes, 200),
        "ema_12": ti.ema(list(closes), 12),
        "ema_26": ti.ema(list(closes), 26),
        "rsi_14": ti.rsi(closes, 14),
        "atr_14": ti.atr(highs, lows, closes, 14),
    }
    series.update(ti.macd(closes))
    series.update(ti.bollinger(closes))
    return series


def _report_for(spec: SeriesSpec, values: ti.Series | None, bars: list[dict]) -> dict:
    report = {
        "key": spec.key,
        "label": spec.label,
        "description": spec.description,
        "parameters": spec.parameters,
        "min_bars": spec.min_bars,
        "status": "NOT_COMPUTABLE",
        "reason": f"Needs at least {spec.min_bars} bars; {len(bars)} available.",
        "warmup_rows": 0,
        "computed_count": 0,
        "undefined_rows": 0,
        "min": None,
        "max": None,
        "latest": None,
        "latest_date": None,
    }
    if values is None:
        return report
    after_warmup = values[spec.min_bars - 1 :]
    defined = [v for v in values if v is not None]
    report.update(
        status="COMPUTED",
        reason=None,
        warmup_rows=spec.min_bars - 1,
        computed_count=len(defined),
        undefined_rows=sum(1 for v in after_warmup if v is None),
        min=float(min(defined)) if defined else None,
        max=float(max(defined)) if defined else None,
        latest=float(values[-1]) if values[-1] is not None else None,
        latest_date=bars[-1]["date"],
    )
    return report


def build_report(bars: list[dict]) -> tuple[list[dict], list[dict], str | None]:
    """Return (indicator reports, preview rows, csv text). csv text is None
    when no series could be computed. `bars` must be ascending by date.
    """
    all_series = _compute_series(bars)
    reports: list[dict] = []
    computed_keys: list[str] = []
    for spec in SERIES_SPECS:
        usable = len(bars) >= spec.min_bars
        reports.append(_report_for(spec, all_series[spec.key] if usable else None, bars))
        if usable:
            computed_keys.append(spec.key)

    if not computed_keys:
        return reports, [], None

    header = ["date", "close", *computed_keys]
    rows = [
        {"date": bar["date"], "close": bar["close"], **{key: all_series[key][i] for key in computed_keys}}
        for i, bar in enumerate(bars)
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if row[column] is None else row[column] for column in header])
    return reports, rows[-PREVIEW_ROWS:], buffer.getvalue()
