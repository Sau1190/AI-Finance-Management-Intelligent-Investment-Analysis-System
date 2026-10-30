"""Phase 9 — risk analysis tests.

The maths is checked three ways: hand-computed values for small inputs, an
independent implementation (pandas/numpy) on random data, and mathematical
properties (a series has beta 1 against itself, CVaR never exceeds VaR, ...).
The API and failure handling mirror the earlier phases. Nothing here judges
whether a number is "high" or "low" risk — Phase 9 only computes and explains.
"""

import json
import logging
import math
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core import database
from app.models.risk_analysis_result import RiskAnalysisResult
from app.services import market_storage, risk_metrics as rm, risk_report, risk_service
from app.services.market_providers import ProviderError

# Reuse earlier phases' helpers rather than duplicating them.
from tests.test_market_data import FakeProvider, use_provider  # noqa: F401
from tests.test_technical import fetch_market, random_walk_bars, typed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def bars_from_closes(closes: list[float], start: date = date(2023, 1, 2), step: int = 1) -> list[dict]:
    """Valid raw (string) bars whose close is exactly the given value."""
    return [
        {
            "date": (start + timedelta(days=i * step)).isoformat(),
            "open": f"{c:.6f}", "high": f"{c * 1.001:.6f}", "low": f"{c * 0.999:.6f}", "close": f"{c:.6f}",
            "volume": "1000",
        }
        for i, c in enumerate(closes)
    ]


def walk_closes(n: int, seed: int, vol: float = 0.01, drift: float = 0.0003) -> list[float]:
    rng = random.Random(seed)
    price, closes = 100.0, []
    for _ in range(n):
        price *= 1 + rng.gauss(drift, vol)
        closes.append(price)
    return closes


def returns_of(seed: int, n: int = 300, vol: float = 0.01) -> list[float]:
    return rm.simple_returns(walk_closes(n, seed, vol))


def by_key(result: dict) -> dict[str, dict]:
    return {m["key"]: m for m in result["metrics"]}


def analyze(client: TestClient, use_provider, closes: list[float], benchmark: list[float] | None = None) -> dict:
    fetch_market(client, use_provider, bars_from_closes(closes), "AAA")
    url = "/api/risk/AAA"
    if benchmark is not None:
        fetch_market(client, use_provider, bars_from_closes(benchmark), "BBB")
        url += "?benchmark=BBB"
    response = client.post(url)
    assert response.status_code == 201, response.text
    return response.json()


def all_results() -> list[RiskAnalysisResult]:
    db = database.SessionLocal()
    try:
        return db.query(RiskAnalysisResult).all()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Pure maths — hand-computed
# ---------------------------------------------------------------------------


def test_simple_returns_hand_example() -> None:
    assert rm.simple_returns([100, 110, 99]) == pytest.approx([0.1, -0.1])
    assert rm.simple_returns([100]) == []


def test_sample_standard_deviation_uses_n_minus_1() -> None:
    assert rm.sample_std([0.1, -0.1]) == pytest.approx(math.sqrt(0.02))  # not sqrt(0.01)
    assert rm.sample_std([1.0, 2.0, 3.0, 4.0]) == pytest.approx(math.sqrt(5 / 3))


def test_quantile_interpolates_linearly_between_order_statistics() -> None:
    values = [5.0, 1.0, 4.0, 2.0, 3.0]  # order must not matter
    assert rm.quantile(values, 0.25) == pytest.approx(2.0)
    assert rm.quantile(values, 0.10) == pytest.approx(1.4)
    assert rm.quantile(values, 0.0) == 1.0 and rm.quantile(values, 1.0) == 5.0
    assert rm.quantile([7.0], 0.05) == 7.0


def test_max_drawdown_hand_example_with_recovery() -> None:
    d = rm.max_drawdown(list("abcde"), [100, 120, 90, 110, 130])
    assert d == {"value": pytest.approx(-0.25), "peak_date": "b", "trough_date": "c", "recovery_date": "e",
                 "bars_peak_to_trough": 1, "bars_to_recovery": 2}


def test_max_drawdown_without_recovery_and_without_any_drawdown() -> None:
    unrecovered = rm.max_drawdown(list("abcd"), [100, 80, 85, 90])
    assert unrecovered["value"] == pytest.approx(-0.2)
    assert unrecovered["recovery_date"] is None and unrecovered["bars_to_recovery"] is None

    rising = rm.max_drawdown(list("abc"), [100, 101, 102])
    assert rising["value"] == 0.0
    assert rising["peak_date"] is None and rising["trough_date"] is None and rising["recovery_date"] is None


def test_max_drawdown_picks_the_worst_of_several_and_counts_equal_price_as_recovery() -> None:
    d = rm.max_drawdown(list("abcdefg"), [100, 95, 100, 150, 90, 120, 160])
    assert d["value"] == pytest.approx(90 / 150 - 1) and d["peak_date"] == "d" and d["trough_date"] == "e"
    assert d["recovery_date"] == "g"
    assert rm.max_drawdown(list("abc"), [100, 90, 100])["recovery_date"] == "c"  # back to the peak counts


def test_max_drawdown_matches_pandas_on_random_data() -> None:
    closes = walk_closes(500, 11, vol=0.02)
    dates = [f"{i:04d}" for i in range(500)]
    s = pd.Series(closes, index=dates)
    expected = (s / s.cummax() - 1)
    got = rm.max_drawdown(dates, closes)
    assert got["value"] == pytest.approx(expected.min())
    assert got["trough_date"] == expected.idxmin()


def test_current_drawdown() -> None:
    at_high = rm.current_drawdown(list("abc"), [100, 90, 110])
    assert at_high["value"] == 0.0 and at_high["peak_date"] == "c"
    below = rm.current_drawdown(list("abcd"), [100, 150, 150, 120])
    assert below["value"] == pytest.approx(-0.2)
    assert below["peak_date"] == "c"  # the most recent high, not the first
    assert below["peak_close"] == 150 and below["latest_close"] == 120


def test_var_and_cvar_hand_example() -> None:
    returns = [-0.10, -0.08, -0.06] + [0.01 * i for i in range(18)]  # 21 returns -> VaR index (21-1)*0.05 = 1.0
    var, cvar = rm.historical_var_cvar(returns)
    assert var == pytest.approx(-0.08)
    assert cvar == pytest.approx((-0.10 - 0.08) / 2)  # mean of the returns at or below VaR


# ---------------------------------------------------------------------------
# Pure maths — independent implementation and properties
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_volatility_var_and_cvar_match_pandas(seed) -> None:
    returns = returns_of(seed, 400, vol=0.015)
    s = pd.Series(returns)
    assert rm.sample_std(returns) == pytest.approx(s.std(ddof=1))
    var, cvar = rm.historical_var_cvar(returns)
    assert var == pytest.approx(s.quantile(0.05))
    assert cvar == pytest.approx(s[s <= s.quantile(0.05)].mean())


def test_cvar_is_never_better_than_var() -> None:
    for seed in range(10):
        var, cvar = rm.historical_var_cvar(returns_of(seed, 250))
        assert cvar <= var


def test_beta_and_correlation_match_numpy() -> None:
    bench, asset = returns_of(5, 300), returns_of(6, 300, vol=0.02)
    beta, corr = rm.beta_correlation(asset, bench)
    assert beta == pytest.approx(np.cov(asset, bench)[0, 1] / np.var(bench, ddof=1))
    assert corr == pytest.approx(np.corrcoef(asset, bench)[0, 1])


def test_beta_and_correlation_known_relationships() -> None:
    bench = returns_of(7, 200)
    assert rm.beta_correlation(bench, bench) == (pytest.approx(1.0), pytest.approx(1.0))
    assert rm.beta_correlation([2 * r for r in bench], bench) == (pytest.approx(2.0), pytest.approx(1.0))
    assert rm.beta_correlation([-r for r in bench], bench) == (pytest.approx(-1.0), pytest.approx(-1.0))
    assert rm.beta_correlation([0.01] * 200, bench)[0] == pytest.approx(0.0)  # a flat asset has zero beta


def test_beta_is_undefined_when_the_benchmark_never_moves() -> None:
    beta, corr = rm.beta_correlation(returns_of(8, 100), [0.0] * 99)
    assert beta is None and corr is None


def test_alignment_uses_only_common_dates_and_returns_span_the_gap() -> None:
    asset = [{"date": d, "close": c} for d, c in [("d1", 100.0), ("d2", 110.0), ("d3", 121.0), ("d4", 133.1)]]
    bench = [{"date": d, "close": c} for d, c in [("d1", 100.0), ("d2", 105.0), ("d4", 115.5)]]  # d3 missing
    dates, a, b = rm.align_on_common_dates(asset, bench)
    assert dates == ["d1", "d2", "d4"] and a == [100.0, 110.0, 133.1] and b == [100.0, 105.0, 115.5]
    # The asset's 2nd return is d2 -> d4 (1.21), matching the benchmark's holding period, not d3 -> d4.
    assert rm.simple_returns(a) == pytest.approx([0.10, 0.21])
    assert rm.simple_returns(b) == pytest.approx([0.05, 0.10])


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def test_full_report_computes_every_metric_consistently_with_the_maths() -> None:
    closes, bench_closes = walk_closes(300, 21, 0.02), walk_closes(300, 22, 0.012)
    bars, bench = typed(bars_from_closes(closes)), typed(bars_from_closes(bench_closes))
    metrics, warnings, n = risk_report.build_report("AAA", bars, "BBB", bench)
    m = {x["key"]: x for x in metrics}
    returns = rm.simple_returns([b["close"] for b in bars])

    assert n == 299 and len(metrics) == 10 and all(x["status"] == "COMPUTED" for x in metrics)
    assert m["daily_volatility"]["value"] == pytest.approx(rm.sample_std(returns))
    assert m["annualized_volatility"]["value"] == pytest.approx(rm.sample_std(returns) * math.sqrt(252))
    assert m["annualized_volatility"]["parameters"] == {"trading_days_per_year": 252}
    assert m["max_drawdown"]["value"] == pytest.approx(rm.max_drawdown([b["date"] for b in bars], [b["close"] for b in bars])["value"])
    assert m["historical_cvar_95"]["value"] <= m["historical_var_95"]["value"]
    assert m["historical_cvar_95"]["details"]["tail_observations"] >= 1
    assert m["beta"]["details"] == {"benchmark": "BBB", "aligned_returns": 299,
                                    "aligned_start": bars[0]["date"], "aligned_end": bars[-1]["date"]}
    assert warnings == []


def test_worst_and_best_day_report_the_date_of_the_move() -> None:
    bars = typed(bars_from_closes([100, 110, 99, 120]))
    m = {x["key"]: x for x in risk_report.build_report("AAA", bars)[0]}
    assert m["worst_day"]["value"] == pytest.approx(-0.1)
    assert m["worst_day"]["details"] == {"date": "2023-01-04", "previous_date": "2023-01-03"}
    assert m["best_day"]["value"] == pytest.approx(120 / 99 - 1)
    assert m["best_day"]["details"]["date"] == "2023-01-05"


def test_short_history_reports_exactly_what_is_missing() -> None:
    bars = typed(bars_from_closes(walk_closes(10, 1)))
    m = {x["key"]: x for x in risk_report.build_report("AAA", bars)[0]}
    assert m["daily_volatility"]["status"] == "NOT_COMPUTABLE"
    assert m["daily_volatility"]["reason"] == "Needs at least 20 daily returns; 9 available."
    assert m["historical_var_95"]["reason"] == "Needs at least 100 daily returns; 9 available."
    assert m["beta"]["reason"] == "No benchmark symbol was given." and m["correlation"]["status"] == "NOT_COMPUTABLE"
    assert m["max_drawdown"]["status"] == m["current_drawdown"]["status"] == "COMPUTED"
    assert m["worst_day"]["status"] == m["best_day"]["status"] == "COMPUTED"
    assert all(x["value"] is None for x in m.values() if x["status"] == "NOT_COMPUTABLE")


@pytest.mark.parametrize(
    "returns_available, metric, expected",
    [(19, "daily_volatility", "NOT_COMPUTABLE"), (20, "daily_volatility", "COMPUTED"),
     (99, "historical_var_95", "NOT_COMPUTABLE"), (100, "historical_var_95", "COMPUTED"),
     (99, "historical_cvar_95", "NOT_COMPUTABLE"), (100, "historical_cvar_95", "COMPUTED")],
)
def test_minimum_history_boundaries(returns_available, metric, expected) -> None:
    bars = typed(bars_from_closes(walk_closes(returns_available + 1, 3)))
    m = {x["key"]: x for x in risk_report.build_report("AAA", bars)[0]}
    assert m[metric]["status"] == expected


@pytest.mark.parametrize("aligned_returns, expected", [(59, "NOT_COMPUTABLE"), (60, "COMPUTED")])
def test_beta_needs_enough_aligned_returns(aligned_returns, expected) -> None:
    bars = typed(bars_from_closes(walk_closes(100, 4)))
    bench = typed(bars_from_closes(walk_closes(100, 5)))[: aligned_returns + 1]  # shares exactly this many dates
    m = {x["key"]: x for x in risk_report.build_report("AAA", bars, "BBB", bench)[0]}
    assert m["beta"]["status"] == expected and m["correlation"]["status"] == expected
    if expected == "NOT_COMPUTABLE":
        assert m["beta"]["reason"] == f"Needs at least 60 aligned daily returns; {aligned_returns} available."


def test_two_bars_is_the_minimum_for_any_metric() -> None:
    m = {x["key"]: x for x in risk_report.build_report("AAA", typed(bars_from_closes([100, 90])))[0]}
    assert m["max_drawdown"]["value"] == pytest.approx(-0.1)
    assert m["worst_day"]["value"] == pytest.approx(-0.1) and m["best_day"]["value"] == pytest.approx(-0.1)
    assert m["daily_volatility"]["status"] == "NOT_COMPUTABLE"
    empty = {x["key"]: x for x in risk_report.build_report("AAA", typed(bars_from_closes([100])))[0]}
    assert all(x["status"] == "NOT_COMPUTABLE" for x in empty.values())


def test_a_split_like_move_is_flagged_but_never_repaired() -> None:
    closes = walk_closes(150, 6)
    closes[100:] = [c * 0.5 for c in closes[100:]]  # an unadjusted 2:1 split: price halves and STAYS lower
    bars = typed(bars_from_closes(closes))
    metrics, warnings, _ = risk_report.build_report("AAA", bars)
    m = {x["key"]: x for x in metrics}

    assert len(warnings) == 1
    expected_move = closes[100] / closes[99] - 1  # the halving stacks with that day's ordinary move
    assert "larger than 30%" in warnings[0] and f"{expected_move:+.1%}" in warnings[0]
    assert bars[100]["date"] in warnings[0]
    assert "unadjusted" in warnings[0] and "not adjusted" in warnings[0] and "AAA" in warnings[0]
    assert m["worst_day"]["value"] == pytest.approx(closes[100] / closes[99] - 1)  # raw data used as received
    assert m["worst_day"]["value"] < -0.45


def test_a_crash_and_rebound_reports_the_count_and_the_largest_move() -> None:
    closes = walk_closes(150, 6)
    closes[100] = closes[99] * 0.5  # one bad bar: -50% then a ~+97% rebound to the old path
    _, warnings, _ = risk_report.build_report("AAA", typed(bars_from_closes(closes)))
    assert len(warnings) == 1 and warnings[0].startswith("2 daily move(s) larger than 30%")
    assert "largest +9" in warnings[0]  # the rebound is the larger absolute move


def test_benchmark_large_moves_are_flagged_under_the_benchmarks_name() -> None:
    bench_closes = walk_closes(100, 8)
    bench_closes[50] *= 0.4
    metrics, warnings, _ = risk_report.build_report(
        "AAA", typed(bars_from_closes(walk_closes(100, 7))), "SPY", typed(bars_from_closes(bench_closes))
    )
    assert len(warnings) >= 1 and all("SPY" in w for w in warnings) and not any("in AAA" in w for w in warnings)


def test_a_flat_price_series_gives_zero_risk_and_undefined_beta() -> None:
    closes = [50.0] * 150
    bars, bench = typed(bars_from_closes(closes)), typed(bars_from_closes(walk_closes(150, 9)))
    m = {x["key"]: x for x in risk_report.build_report("AAA", bars, "BBB", bench)[0]}
    assert m["daily_volatility"]["value"] == 0.0 and m["max_drawdown"]["value"] == 0.0
    assert m["historical_var_95"]["value"] == 0.0 and m["max_drawdown"]["details"]["peak_date"] is None
    # Zero-variance asset: beta is 0 (defined), correlation is undefined — never a made-up number.
    assert m["beta"]["status"] == "COMPUTED" and m["beta"]["value"] == pytest.approx(0.0)
    assert m["correlation"]["status"] == "NOT_COMPUTABLE" and "no variance" in m["correlation"]["reason"]


def test_a_constant_benchmark_leaves_beta_and_correlation_undefined() -> None:
    bars = typed(bars_from_closes(walk_closes(150, 10)))
    bench = typed(bars_from_closes([100.0] * 150))
    m = {x["key"]: x for x in risk_report.build_report("AAA", bars, "BBB", bench)[0]}
    assert m["beta"]["status"] == m["correlation"]["status"] == "NOT_COMPUTABLE"
    assert "no variance" in m["beta"]["reason"]


def test_report_values_are_native_floats_and_contain_no_risk_judgements() -> None:
    metrics, warnings, _ = risk_report.build_report(
        "AAA", typed(bars_from_closes(walk_closes(200, 12))), "BBB", typed(bars_from_closes(walk_closes(200, 13)))
    )
    for metric in metrics:
        assert metric["value"] is None or type(metric["value"]) is float
        for detail in metric["details"].values():
            assert type(detail) in (str, int, float, type(None))
    text = json.dumps(metrics).lower()
    for phrase in ("high risk", "low risk", "risky", "safe", "dangerous", "recommend"):
        assert phrase not in text


# ---------------------------------------------------------------------------
# API — successful runs
# ---------------------------------------------------------------------------


def test_analysis_with_a_benchmark_records_which_snapshots_it_used(client: TestClient, use_provider) -> None:
    asset, bench = walk_closes(300, 31, 0.02), walk_closes(300, 32, 0.012)
    asset_market = fetch_market(client, use_provider, bars_from_closes(asset), "AAA")
    bench_market = fetch_market(client, use_provider, bars_from_closes(bench), "BBB")

    response = client.post("/api/risk/aaa?benchmark=bbb")
    body = response.json()
    assert response.status_code == 201 and body["status"] == "COMPLETE"
    assert (body["symbol"], body["benchmark_symbol"]) == ("AAA", "BBB")
    assert body["market_snapshot_id"] == asset_market["id"] and body["benchmark_snapshot_id"] == bench_market["id"]
    assert (body["bar_count"], body["returns_count"]) == (300, 299)
    assert (body["first_date"], body["last_date"]) == ("2023-01-02", (date(2023, 1, 2) + timedelta(days=299)).isoformat())

    m = by_key(body)
    returns = rm.simple_returns([float(f"{c:.6f}") for c in asset])
    assert m["daily_volatility"]["value"] == pytest.approx(rm.sample_std(returns))
    assert all(x["status"] == "COMPUTED" for x in body["metrics"])


def test_analysis_without_a_benchmark_skips_beta_with_a_reason(client: TestClient, use_provider) -> None:
    body = analyze(client, use_provider, walk_closes(300, 33))
    m = by_key(body)
    assert body["benchmark_symbol"] is None and body["benchmark_snapshot_id"] is None
    assert m["beta"]["status"] == "NOT_COMPUTABLE" and m["beta"]["reason"] == "No benchmark symbol was given."
    assert m["daily_volatility"]["status"] == "COMPUTED"


def test_benchmark_with_missing_days_aligns_on_common_dates(client: TestClient, use_provider) -> None:
    asset_bars = bars_from_closes(walk_closes(300, 34))
    bench_bars = [b for i, b in enumerate(bars_from_closes(walk_closes(300, 35))) if i % 11 != 5]
    fetch_market(client, use_provider, asset_bars, "AAA")
    fetch_market(client, use_provider, bench_bars, "BBB")
    body = client.post("/api/risk/AAA?benchmark=BBB").json()

    common = len({b["date"] for b in asset_bars} & {b["date"] for b in bench_bars})
    detail = by_key(body)["beta"]["details"]
    assert detail["aligned_returns"] == common - 1
    assert detail["aligned_returns"] < body["returns_count"]


def test_large_moves_surface_as_warnings_in_the_result(client: TestClient, use_provider) -> None:
    closes = walk_closes(200, 36)
    closes[120:] = [c * 0.5 for c in closes[120:]]
    body = analyze(client, use_provider, closes)
    assert body["status"] == "COMPLETE" and len(body["warnings"]) == 1
    assert "stock split" in body["warnings"][0]
    assert by_key(body)["worst_day"]["value"] < -0.45  # reported as received, not repaired


def test_result_traces_the_snapshot_and_a_new_fetch_gives_a_new_result(client: TestClient, use_provider) -> None:
    first_market = fetch_market(client, use_provider, bars_from_closes(walk_closes(100, 37)), "AAA")
    first = client.post("/api/risk/AAA").json()
    second_market = fetch_market(client, use_provider, bars_from_closes(walk_closes(150, 38)), "AAA")
    second = client.post("/api/risk/AAA").json()

    assert first["market_snapshot_id"] == first_market["id"] and second["market_snapshot_id"] == second_market["id"]
    assert (first["bar_count"], second["bar_count"]) == (100, 150)
    assert client.get("/api/risk/AAA").json()["id"] == second["id"]


def test_a_newer_failed_fetch_does_not_hide_good_data(client: TestClient, use_provider) -> None:
    good = fetch_market(client, use_provider, bars_from_closes(walk_closes(100, 39)), "AAA")
    use_provider(FakeProvider(error=ProviderError("PROVIDER_DECLINED_REQUEST", "Try later.")))
    assert client.post("/api/market-data/AAA").json()["status"] == "FAILED"
    body = client.post("/api/risk/AAA").json()
    assert body["status"] == "COMPLETE" and body["market_snapshot_id"] == good["id"]


def test_phase6_price_files_are_never_modified(client: TestClient, use_provider) -> None:
    market = fetch_market(client, use_provider, bars_from_closes(walk_closes(100, 40)), "AAA")
    path = market_storage.market_directory() / Path(market["bars_storage_key"]).name
    before = path.read_bytes()
    client.post("/api/risk/AAA")
    assert path.read_bytes() == before


def test_results_are_per_symbol(client: TestClient, use_provider) -> None:
    analyze(client, use_provider, walk_closes(100, 41))
    assert client.get("/api/risk/BBB").status_code == 404


# ---------------------------------------------------------------------------
# API — invalid input and missing prerequisites
# ---------------------------------------------------------------------------


def test_analysis_without_market_data_returns_404(client: TestClient) -> None:
    response = client.post("/api/risk/AAA")
    assert response.status_code == 404 and response.json()["detail"]["code"] == "MARKET_DATA_NOT_FOUND"


def test_a_benchmark_without_market_data_returns_404(client: TestClient, use_provider) -> None:
    fetch_market(client, use_provider, bars_from_closes(walk_closes(100, 42)), "AAA")
    response = client.post("/api/risk/AAA?benchmark=SPY")
    assert response.status_code == 404 and response.json()["detail"]["code"] == "BENCHMARK_DATA_NOT_FOUND"
    assert all_results() == []


def test_a_symbol_with_only_failed_fetches_counts_as_having_no_data(client: TestClient, use_provider) -> None:
    use_provider(FakeProvider(error=ProviderError("PROVIDER_TIMEOUT", "Slow.")))
    client.post("/api/market-data/AAA")
    assert client.post("/api/risk/AAA").json()["detail"]["code"] == "MARKET_DATA_NOT_FOUND"


@pytest.mark.parametrize("bad", ["A%20B", "-AAPL", "TOOLONGSYMBOL", "AAP%24"])
def test_invalid_symbols_and_benchmarks_are_rejected(client: TestClient, bad) -> None:
    for response in (client.post(f"/api/risk/{bad}"), client.get(f"/api/risk/{bad}"),
                     client.post(f"/api/risk/AAA?benchmark={bad}")):
        assert response.status_code == 400 and response.json()["detail"]["code"] == "INVALID_SYMBOL"


@pytest.mark.parametrize("benchmark", ["AAA", "aaa"])
def test_a_benchmark_equal_to_the_symbol_is_rejected(client: TestClient, use_provider, benchmark) -> None:
    fetch_market(client, use_provider, bars_from_closes(walk_closes(100, 43)), "AAA")
    response = client.post(f"/api/risk/AAA?benchmark={benchmark}")
    assert response.status_code == 400 and response.json()["detail"]["code"] == "INVALID_BENCHMARK"
    assert all_results() == []


def test_get_before_any_analysis_returns_404(client: TestClient) -> None:
    response = client.get("/api/risk/AAA")
    assert response.status_code == 404 and response.json()["detail"]["code"] == "RISK_RESULT_NOT_FOUND"


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


def test_a_single_bar_is_a_failed_run(client: TestClient, use_provider) -> None:
    body = analyze(client, use_provider, [100.0])
    assert body["status"] == "FAILED" and body["error_code"] == "INSUFFICIENT_DATA"
    assert "1 bar(s) available" in body["error_message"] and body["metrics"] == []
    assert client.get("/api/risk/AAA").json()["status"] == "FAILED"


@pytest.mark.parametrize("which", ["asset", "benchmark"])
def test_missing_stored_price_files_fail_the_run_cleanly(client: TestClient, use_provider, which) -> None:
    asset = fetch_market(client, use_provider, bars_from_closes(walk_closes(100, 44)), "AAA")
    bench = fetch_market(client, use_provider, bars_from_closes(walk_closes(100, 45)), "BBB")
    target = asset if which == "asset" else bench
    (market_storage.market_directory() / Path(target["bars_storage_key"]).name).unlink()
    body = client.post("/api/risk/AAA?benchmark=BBB").json()
    assert body["status"] == "FAILED" and body["error_code"] == "MARKET_DATA_UNAVAILABLE"
    assert body["metrics"] == [] and body["market_snapshot_id"] == asset["id"]


def test_unexpected_computation_error_fails_without_leaking(client: TestClient, use_provider, monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    fetch_market(client, use_provider, bars_from_closes(walk_closes(100, 46)), "AAA")

    def exploding(*_args, **_kwargs):
        raise RuntimeError("boom internal detail /srv/secret/path")

    monkeypatch.setattr(risk_report, "build_report", exploding)
    response = client.post("/api/risk/AAA")
    body = response.json()
    assert body["status"] == "FAILED" and body["error_code"] == "RISK_ANALYSIS_FAILURE"
    assert "boom" not in response.text and "/srv/secret" not in response.text
    assert "boom" not in caplog.text, "only the exception type may be logged"


def test_database_failure_propagates_and_stores_nothing(client: TestClient, use_provider, monkeypatch) -> None:
    fetch_market(client, use_provider, bars_from_closes(walk_closes(100, 47)), "AAA")
    db = database.SessionLocal()
    try:
        def failing_commit():
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(db, "commit", failing_commit)
        with pytest.raises(RuntimeError):
            risk_service.analyze_risk(db, "AAA")
    finally:
        db.close()
    assert all_results() == []
