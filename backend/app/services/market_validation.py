"""Deterministic validation of raw provider bars.

Provider-independent. A bar is accepted exactly as received or rejected with a
counted reason — values are never rounded, clamped, interpolated, or "fixed".
Rejected bars are reported, not hidden, so a caller always knows how much of
what the provider sent was actually usable.

Not modelled: stock splits and dividends. Daily bars from TIME_SERIES_DAILY
are as-traded (unadjusted), so a split appears as a price discontinuity.
"""

import math
import re
from collections import Counter
from datetime import date, timedelta

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PRICE_FIELDS = ("open", "high", "low", "close")

# Exchange-local dates can run up to a day ahead of UTC, so tolerate +1 day.
FUTURE_TOLERANCE = timedelta(days=1)


def _finite_number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def validate_bars(raw_bars: list[dict], today: date) -> tuple[list[dict], Counter]:
    """Return (valid_bars sorted by date ascending, rejected reason counts).
    Valid bars use native types: date as ISO str, prices as float, volume as int.
    """
    rejected: Counter = Counter()
    parsed: list[dict] = []

    for raw in raw_bars:
        raw_date = raw.get("date")
        if not isinstance(raw_date, str) or not _ISO_DATE.match(raw_date.strip()):
            rejected["invalid date"] += 1
            continue
        try:
            bar_date = date.fromisoformat(raw_date.strip())
        except ValueError:
            rejected["invalid date"] += 1
            continue
        if bar_date > today + FUTURE_TOLERANCE:
            rejected["future date"] += 1
            continue

        prices: dict[str, float] = {}
        reason = None
        for field in _PRICE_FIELDS:
            number = _finite_number(raw.get(field))
            if number is None:
                reason = f"non-numeric {field}"
                break
            if number <= 0:
                reason = f"non-positive {field}"
                break
            prices[field] = number
        if reason is None:
            volume = _finite_number(raw.get("volume"))
            if volume is None or volume < 0 or volume != int(volume):
                reason = "invalid volume"
            elif prices["high"] < prices["low"]:
                reason = "high below low"
            elif not (prices["low"] <= prices["open"] <= prices["high"]):
                reason = "open outside high/low range"
            elif not (prices["low"] <= prices["close"] <= prices["high"]):
                reason = "close outside high/low range"
        if reason is not None:
            rejected[reason] += 1
            continue

        parsed.append({"date": bar_date.isoformat(), **prices, "volume": int(volume)})

    # A repeated date is ambiguous: we cannot tell which bar is right, so
    # neither is kept (and both are counted) rather than picking one.
    date_counts = Counter(bar["date"] for bar in parsed)
    valid = [bar for bar in parsed if date_counts[bar["date"]] == 1]
    duplicates = len(parsed) - len(valid)
    if duplicates:
        rejected["duplicate date"] += duplicates

    valid.sort(key=lambda bar: bar["date"])
    return valid, rejected
