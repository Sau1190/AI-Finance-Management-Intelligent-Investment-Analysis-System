"""Turns price bars into an explainable risk report.

Pure (no database, no storage). Each metric states its definition, parameters,
the history it needs, and — when it cannot be computed — exactly why. Nothing
is approximated from too little data, and nothing is labelled "high"/"low"
risk: that interpretation belongs to the scoring phase.
"""

import math
from dataclasses import dataclass

from app.services import risk_metrics as rm


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    description: str
    parameters: dict
    min_returns: int


SPECS: tuple[MetricSpec, ...] = (
    MetricSpec("daily_volatility", "Daily volatility",
               "Sample standard deviation (n-1) of daily simple returns.", {}, rm.MIN_RETURNS_VOLATILITY),
    MetricSpec("annualized_volatility", "Annualized volatility",
               "Daily volatility x sqrt(252). The 252 trading days per year is a convention, not a measurement.",
               {"trading_days_per_year": rm.TRADING_DAYS_PER_YEAR}, rm.MIN_RETURNS_VOLATILITY),
    MetricSpec("max_drawdown", "Maximum drawdown",
               "Largest peak-to-trough fall of the close: close / running peak - 1 (negative).", {}, 1),
    MetricSpec("current_drawdown", "Current drawdown",
               "Latest close / highest close in the window - 1 (0 at a new high).", {}, 1),
    MetricSpec("worst_day", "Worst day", "Lowest single-day close-to-close return.", {}, 1),
    MetricSpec("best_day", "Best day", "Highest single-day close-to-close return.", {}, 1),
    MetricSpec("historical_var_95", "Historical VaR (95%)",
               "5th percentile of daily returns (linear interpolation). -0.02 = a 2% one-day loss or worse on ~5% of days.",
               {"level": rm.VAR_LEVEL}, rm.MIN_RETURNS_VAR),
    MetricSpec("historical_cvar_95", "Historical CVaR (95%)",
               "Mean of the daily returns at or below the historical VaR.", {"level": rm.VAR_LEVEL}, rm.MIN_RETURNS_VAR),
    MetricSpec("beta", "Beta vs benchmark",
               "cov(asset, benchmark) / var(benchmark) of returns between consecutive common dates.",
               {}, rm.MIN_ALIGNED_RETURNS_BETA),
    MetricSpec("correlation", "Correlation vs benchmark",
               "Pearson correlation of the same aligned returns.", {}, rm.MIN_ALIGNED_RETURNS_BETA),
)


def _entry(spec: MetricSpec, *, status="NOT_COMPUTABLE", reason=None, value=None, details=None) -> dict:
    return {
        "key": spec.key,
        "label": spec.label,
        "description": spec.description,
        "parameters": spec.parameters,
        "min_returns": spec.min_returns,
        "status": status,
        "reason": reason,
        "value": value,
        "details": details or {},
    }


def _short(spec: MetricSpec, available: int, what: str = "daily returns") -> dict:
    return _entry(spec, reason=f"Needs at least {spec.min_returns} {what}; {available} available.")


def _large_move_warning(name: str, dates: list[str], returns: list[float]) -> str | None:
    big = [(abs(r), r, dates[i + 1]) for i, r in enumerate(returns) if abs(r) > rm.LARGE_MOVE_THRESHOLD]
    if not big:
        return None
    _, largest, when = max(big)
    return (
        f"{len(big)} daily move(s) larger than {rm.LARGE_MOVE_THRESHOLD:.0%} in {name} "
        f"(largest {largest:+.1%} on {when}). If this is a stock split in unadjusted prices, "
        "volatility, drawdown, VaR and beta are overstated; prices are not adjusted for splits or dividends."
    )


def build_report(
    symbol: str,
    bars: list[dict],
    benchmark_symbol: str | None = None,
    benchmark_bars: list[dict] | None = None,
) -> tuple[list[dict], list[str], int]:
    """Return (metric reports, warnings, daily return count). `bars` must be
    ascending by date with unique dates.
    """
    dates = [b["date"] for b in bars]
    closes = [b["close"] for b in bars]
    returns = rm.simple_returns(closes)
    n = len(returns)
    by_key = {spec.key: spec for spec in SPECS}
    reports: dict[str, dict] = {}

    for key in ("daily_volatility", "annualized_volatility"):
        spec = by_key[key]
        if n < spec.min_returns:
            reports[key] = _short(spec, n)
            continue
        daily = rm.sample_std(returns)
        value = daily if key == "daily_volatility" else daily * math.sqrt(rm.TRADING_DAYS_PER_YEAR)
        reports[key] = _entry(spec, status="COMPUTED", value=float(value), details={"returns_used": n})

    for key, fn in (("max_drawdown", rm.max_drawdown), ("current_drawdown", rm.current_drawdown)):
        spec = by_key[key]
        if n < spec.min_returns:
            reports[key] = _short(spec, n)
            continue
        details = fn(dates, closes)
        value = details.pop("value")
        reports[key] = _entry(spec, status="COMPUTED", value=float(value), details=details)

    for key, pick in (("worst_day", min), ("best_day", max)):
        spec = by_key[key]
        if n < spec.min_returns:
            reports[key] = _short(spec, n)
            continue
        index = returns.index(pick(returns))  # first occurrence on ties
        reports[key] = _entry(
            spec, status="COMPUTED", value=float(returns[index]),
            details={"date": dates[index + 1], "previous_date": dates[index]},
        )

    spec_var, spec_cvar = by_key["historical_var_95"], by_key["historical_cvar_95"]
    if n < rm.MIN_RETURNS_VAR:
        reports["historical_var_95"] = _short(spec_var, n)
        reports["historical_cvar_95"] = _short(spec_cvar, n)
    else:
        var, cvar = rm.historical_var_cvar(returns)
        tail = sum(1 for r in returns if r <= var)
        reports["historical_var_95"] = _entry(
            spec_var, status="COMPUTED", value=float(var), details={"returns_used": n}
        )
        reports["historical_cvar_95"] = _entry(
            spec_cvar, status="COMPUTED", value=float(cvar), details={"returns_used": n, "tail_observations": tail}
        )

    warnings: list[str] = []
    warning = _large_move_warning(symbol, dates, returns)
    if warning:
        warnings.append(warning)

    beta_spec, corr_spec = by_key["beta"], by_key["correlation"]
    if benchmark_bars is None:
        reports["beta"] = _entry(beta_spec, reason="No benchmark symbol was given.")
        reports["correlation"] = _entry(corr_spec, reason="No benchmark symbol was given.")
    else:
        common, asset_closes, bench_closes = rm.align_on_common_dates(bars, benchmark_bars)
        aligned_n = max(len(common) - 1, 0)
        bench_warning = _large_move_warning(
            benchmark_symbol or "the benchmark", [b["date"] for b in benchmark_bars],
            rm.simple_returns([b["close"] for b in benchmark_bars]),
        )
        if bench_warning:
            warnings.append(bench_warning)
        if aligned_n < rm.MIN_ALIGNED_RETURNS_BETA:
            reports["beta"] = _short(beta_spec, aligned_n, "aligned daily returns")
            reports["correlation"] = _short(corr_spec, aligned_n, "aligned daily returns")
        else:
            beta, correlation = rm.beta_correlation(
                rm.simple_returns(asset_closes), rm.simple_returns(bench_closes)
            )
            details = {
                "benchmark": benchmark_symbol,
                "aligned_returns": aligned_n,
                "aligned_start": common[0],
                "aligned_end": common[-1],
            }
            for key, value in (("beta", beta), ("correlation", correlation)):
                spec = by_key[key]
                if value is None:
                    reports[key] = _entry(
                        spec, reason="The benchmark or asset returns have no variance, so this is undefined.",
                        details=details,
                    )
                else:
                    reports[key] = _entry(spec, status="COMPUTED", value=float(value), details=details)

    return [reports[spec.key] for spec in SPECS], warnings, n
