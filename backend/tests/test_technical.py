"""Phase 7 — technical analysis tests.

Indicator maths is checked three ways: hand-computed values for small inputs,
an independent implementation (pandas) for SMA and Bollinger bands, and a
published external reference series for RSI. The API and storage guarantees
mirror the earlier phases. Nothing here judges what an indicator "means" —
Phase 7 only computes and explains.
"""

import json
import logging
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core import database
from app.core.exceptions import AnalysisRequestError
from app.models.technical_analysis_result import TechnicalAnalysisResult
from app.services import (
    analysis_storage,
    market_storage,
    technical_indicators as ti,
    technical_report,
    technical_service,
)
from app.services.market_providers import ProviderError

# Reuse Phase 6's helpers rather than duplicating them.
from tests.test_market_data import FakeProvider, use_provider  # noqa: F401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def random_walk_bars(n: int, seed: int = 7, start: date = date(2023, 1, 2)) -> list[dict]:
    """Raw (string-valued) bars that pass Phase 6 validation."""
    rng = random.Random(seed)
    price, bars = 100.0, []
    for i in range(n):
        o = price
        c = max(1.0, o + rng.uniform(-2, 2))
        h = max(o, c) + rng.uniform(0, 1)
        l = min(o, c) - rng.uniform(0, 1)
        price = c
        bars.append({
            "date": (start + timedelta(days=i)).isoformat(),
            "open": f"{o:.4f}", "high": f"{h:.4f}", "low": f"{l:.4f}", "close": f"{c:.4f}",
            "volume": str(1000 + i),
        })
    return bars


def typed(bars: list[dict]) -> list[dict]:
    return [
        {"date": b["date"], **{k: float(b[k]) for k in ("open", "high", "low", "close")}, "volume": int(b["volume"])}
        for b in bars
    ]


def fetch_market(client: TestClient, use_provider, bars: list[dict], symbol: str = "IBM") -> dict:
    use_provider(FakeProvider(bars))
    response = client.post(f"/api/market-data/{symbol}")
    assert response.status_code == 201 and response.json()["status"] == "COMPLETE", response.text
    return response.json()


def analyze(client: TestClient, use_provider, n: int = 300, symbol: str = "IBM") -> dict:
    fetch_market(client, use_provider, random_walk_bars(n), symbol)
    response = client.post(f"/api/technical/{symbol}")
    assert response.status_code == 201, response.text
    return response.json()


def analysis_files() -> list[str]:
    return sorted(p.name for p in analysis_storage.analysis_directory().iterdir())


def by_key(result: dict) -> dict[str, dict]:
    return {i["key"]: i for i in result["indicators"]}


# Published reference data set for RSI(14) (the widely used worked example).
REFERENCE_CLOSES = [
    44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245, 45.8433, 46.0826, 45.8931, 46.0328,
    45.6140, 46.2820, 46.2820, 46.0028, 46.0328, 46.4116, 46.2222, 45.6439, 46.2122, 46.2521, 45.7137, 46.4515,
    45.7835, 45.3548, 44.0288, 44.1783, 44.2181, 44.5672, 43.4205, 42.6628, 43.1314,
]
REFERENCE_RSI = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97]


# ---------------------------------------------------------------------------
# Pure indicator maths
# ---------------------------------------------------------------------------


def test_sma_hand_example_and_warmup() -> None:
    assert ti.sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]
    assert ti.sma([1, 2], 3) == [None, None]


def test_sma_matches_pandas_on_random_data() -> None:
    closes = [float(b["close"]) for b in random_walk_bars(250)]
    expected = pd.Series(closes).rolling(50).mean().tolist()
    got = ti.sma(closes, 50)
    assert got[:49] == [None] * 49
    assert got[49:] == pytest.approx(expected[49:], abs=1e-9)


def test_ema_is_seeded_with_the_sma_then_recursive() -> None:
    # period 2 -> alpha = 2/3; seed = mean(2, 4) = 3
    result = ti.ema([2.0, 4.0, 6.0, 8.0], 2)
    assert result[0] is None
    assert result[1] == pytest.approx(3.0)
    assert result[2] == pytest.approx(2 / 3 * 6 + 1 / 3 * 3)  # 5.0
    assert result[3] == pytest.approx(2 / 3 * 8 + 1 / 3 * 5)  # 7.0
    assert ti.ema([1.0, 2.0, 3.0, 4.0, 5.0], 3) == [None, None, 2.0, 3.0, 4.0]


def test_ema_starts_after_leading_nones_and_needs_enough_values() -> None:
    assert ti.ema([None, None, 1.0, 2.0, 3.0, 4.0], 3) == [None, None, None, None, 2.0, 3.0]
    assert ti.ema([1.0, 2.0], 3) == [None, None]
    assert ti.ema([None, None], 3) == [None, None]


def test_macd_structure_and_identities() -> None:
    closes = [float(b["close"]) for b in random_walk_bars(120)]
    out = ti.macd(closes)
    fast, slow = ti.ema(closes, 12), ti.ema(closes, 26)
    line, signal, hist = out["macd"], out["macd_signal"], out["macd_histogram"]

    assert line[:25] == [None] * 25 and line[25] is not None
    assert signal[:33] == [None] * 33 and signal[33] is not None
    assert hist[:33] == [None] * 33 and hist[33] is not None
    for i in range(25, 120):
        assert line[i] == pytest.approx(fast[i] - slow[i])
    assert signal == ti.ema(line, 9)
    for i in range(33, 120):
        assert hist[i] == pytest.approx(line[i] - signal[i])


def test_rsi_matches_the_published_reference_series() -> None:
    result = ti.rsi(REFERENCE_CLOSES, 14)
    assert result[:14] == [None] * 14
    assert [round(v, 2) for v in result[14:20]] == REFERENCE_RSI


def test_rsi_extremes_and_undefined_cases() -> None:
    rising = [float(i) for i in range(1, 40)]
    falling = [float(i) for i in range(40, 1, -1)]
    flat = [10.0] * 40
    assert ti.rsi(rising)[14:] == [100.0] * (len(rising) - 14)
    assert ti.rsi(falling)[14:] == [0.0] * (len(falling) - 14)
    assert ti.rsi(flat) == [None] * 40  # no movement: undefined, not an invented 50
    assert ti.rsi([1.0] * 14) == [None] * 14  # fewer than period + 1 prices


def test_rsi_stays_within_0_and_100() -> None:
    closes = [float(b["close"]) for b in random_walk_bars(400, seed=3)]
    values = [v for v in ti.rsi(closes) if v is not None]
    assert values and all(0.0 <= v <= 100.0 for v in values)


def test_bollinger_matches_pandas_population_std() -> None:
    closes = [float(b["close"]) for b in random_walk_bars(120)]
    out = ti.bollinger(closes)
    s = pd.Series(closes)
    mean, std = s.rolling(20).mean(), s.rolling(20).std(ddof=0)
    assert out["bb_middle"][19:] == pytest.approx(mean.tolist()[19:], abs=1e-9)
    assert out["bb_upper"][19:] == pytest.approx((mean + 2 * std).tolist()[19:], abs=1e-9)
    assert out["bb_lower"][19:] == pytest.approx((mean - 2 * std).tolist()[19:], abs=1e-9)
    assert out["bb_upper"][:19] == [None] * 19


def test_bollinger_collapses_on_constant_prices() -> None:
    out = ti.bollinger([50.0] * 30)
    assert out["bb_upper"][-1] == out["bb_middle"][-1] == out["bb_lower"][-1] == 50.0


def test_atr_hand_example() -> None:
    closes = [10.0, 11.0, 12.0, 11.0, 13.0]
    highs = [11.0, 12.0, 13.0, 12.0, 14.0]
    lows = [9.0, 10.0, 11.0, 10.0, 12.0]
    # TR_1..TR_4 = 2, 2, 2, 3 ; first ATR(3) = 2 ; next = (2*2 + 3)/3
    result = ti.atr(highs, lows, closes, 3)
    assert result[:3] == [None, None, None]
    assert result[3] == pytest.approx(2.0)
    assert result[4] == pytest.approx(7 / 3)


def test_atr_true_range_uses_the_previous_close_for_gaps() -> None:
    # Bar 1 gaps far above bar 0's close: high-low is 1, but TR must be 6.
    result = ti.atr([10.0, 16.0], [9.0, 15.0], [10.0, 15.5], 1)
    assert result == [None, pytest.approx(6.0)]


def test_all_indicator_outputs_are_native_python_floats() -> None:
    closes = [float(b["close"]) for b in random_walk_bars(60)]
    bars = typed(random_walk_bars(60))
    outputs = [ti.sma(closes, 20), ti.ema(closes, 12), ti.rsi(closes), ti.atr(
        [b["high"] for b in bars], [b["low"] for b in bars], closes)]
    outputs += list(ti.macd(closes).values()) + list(ti.bollinger(closes).values())
    for series in outputs:
        assert all(v is None or type(v) is float for v in series)


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def test_report_with_ample_history_computes_every_series() -> None:
    bars = typed(random_walk_bars(300))
    reports, preview, csv_text = technical_report.build_report(bars)
    assert len(reports) == 13
    assert all(r["status"] == "COMPUTED" for r in reports)
    lines = csv_text.splitlines()
    assert len(lines) == 301
    assert lines[0] == "date,close," + ",".join(r["key"] for r in reports)
    assert len(preview) == 5 and preview[-1]["date"] == bars[-1]["date"]
    sma200 = next(r for r in reports if r["key"] == "sma_200")
    assert sma200["warmup_rows"] == 199 and sma200["computed_count"] == 101
    assert sma200["latest_date"] == bars[-1]["date"]


def test_report_marks_series_without_enough_history_not_computable() -> None:
    reports, _, csv_text = technical_report.build_report(typed(random_walk_bars(60)))
    keys = {r["key"]: r for r in reports}
    assert keys["sma_200"]["status"] == "NOT_COMPUTABLE"
    assert keys["sma_200"]["reason"] == "Needs at least 200 bars; 60 available."
    assert keys["sma_200"]["computed_count"] == 0 and keys["sma_200"]["latest"] is None
    assert keys["sma_50"]["status"] == "COMPUTED"
    assert keys["macd_signal"]["min_bars"] == 34 and keys["macd_signal"]["status"] == "COMPUTED"
    assert "sma_200" not in csv_text.splitlines()[0]  # never padded or approximated


def test_report_needs_a_minimum_number_of_bars() -> None:
    assert technical_report.MIN_BARS_FOR_ANY == 12
    _, _, none = technical_report.build_report(typed(random_walk_bars(11)))
    assert none is None
    reports, _, csv_text = technical_report.build_report(typed(random_walk_bars(12)))
    assert [r["key"] for r in reports if r["status"] == "COMPUTED"] == ["ema_12"]
    assert csv_text.splitlines()[0] == "date,close,ema_12"


def test_report_counts_undefined_rows_separately_from_warmup() -> None:
    flat = typed([{"date": (date(2023, 1, 2) + timedelta(days=i)).isoformat(), "open": "10", "high": "10",
                   "low": "10", "close": "10", "volume": "1"} for i in range(30)])
    reports, _, _ = technical_report.build_report(flat)
    rsi = next(r for r in reports if r["key"] == "rsi_14")
    assert rsi["status"] == "COMPUTED"
    assert rsi["warmup_rows"] == 14 and rsi["undefined_rows"] == 16 and rsi["computed_count"] == 0
    assert rsi["latest"] is None and rsi["min"] is None


# ---------------------------------------------------------------------------
# API — successful runs
# ---------------------------------------------------------------------------


def test_analysis_computes_indicators_from_the_stored_market_data(client: TestClient, use_provider) -> None:
    raw = random_walk_bars(300)
    market = fetch_market(client, use_provider, raw)
    response = client.post("/api/technical/ibm")
    assert response.status_code == 201
    body = response.json()

    assert body["status"] == "COMPLETE" and body["symbol"] == "IBM"
    assert body["market_snapshot_id"] == market["id"]
    assert body["bar_count"] == 300
    assert (body["first_date"], body["last_date"]) == (raw[0]["date"], raw[-1]["date"])
    assert len(body["indicators"]) == 13 and all(i["status"] == "COMPUTED" for i in body["indicators"])

    closes = [float(b["close"]) for b in raw]
    expected_latest = {
        "sma_20": ti.sma(closes, 20)[-1],
        "ema_26": ti.ema(closes, 26)[-1],
        "rsi_14": ti.rsi(closes)[-1],
        "macd_histogram": ti.macd(closes)["macd_histogram"][-1],
        "bb_upper": ti.bollinger(closes)["bb_upper"][-1],
    }
    indicators = by_key(body)
    for key, value in expected_latest.items():
        assert indicators[key]["latest"] == pytest.approx(value), key
    assert indicators["sma_20"]["latest"] == pytest.approx(pd.Series(closes).rolling(20).mean().iloc[-1])

    assert body["indicators_storage_key"].startswith("analysis/")
    assert analysis_files() == [Path(body["indicators_storage_key"]).name]
    assert len(body["preview_rows"]) == 5 and body["preview_rows"][-1]["date"] == raw[-1]["date"]


def test_short_history_reports_what_is_missing_and_why(client: TestClient, use_provider) -> None:
    body = analyze(client, use_provider, n=60)
    assert body["status"] == "COMPLETE"
    indicators = by_key(body)
    assert indicators["sma_200"]["status"] == "NOT_COMPUTABLE"
    assert "Needs at least 200 bars; 60 available." == indicators["sma_200"]["reason"]
    assert indicators["sma_50"]["status"] == "COMPUTED"
    stored = analysis_storage.read_csv_rows(body["indicators_storage_key"])
    assert "sma_200" not in stored[0] and "sma_50" in stored[0]


def test_too_little_history_is_a_failed_run_without_an_artifact(client: TestClient, use_provider) -> None:
    body = analyze(client, use_provider, n=10)
    assert body["status"] == "FAILED" and body["error_code"] == "INSUFFICIENT_DATA"
    assert "10 bars available" in body["error_message"]
    assert body["indicators"] == [] and body["indicators_storage_key"] is None
    assert analysis_files() == []


def test_result_traces_the_market_snapshot_it_used(client: TestClient, use_provider) -> None:
    first_market = fetch_market(client, use_provider, random_walk_bars(100))
    first = client.post("/api/technical/IBM").json()
    second_market = fetch_market(client, use_provider, random_walk_bars(120, seed=9))
    second = client.post("/api/technical/IBM").json()

    assert first["market_snapshot_id"] == first_market["id"]
    assert second["market_snapshot_id"] == second_market["id"]
    assert first["market_snapshot_id"] != second["market_snapshot_id"]
    assert second["bar_count"] == 120
    assert client.get("/api/technical/IBM").json()["id"] == second["id"]


def test_a_newer_failed_market_fetch_does_not_hide_good_data(client: TestClient, use_provider) -> None:
    good = fetch_market(client, use_provider, random_walk_bars(100))
    use_provider(FakeProvider(error=ProviderError("PROVIDER_DECLINED_REQUEST", "Try later.")))
    assert client.post("/api/market-data/IBM").json()["status"] == "FAILED"

    body = client.post("/api/technical/IBM").json()
    assert body["status"] == "COMPLETE" and body["market_snapshot_id"] == good["id"]


def test_results_contain_no_trading_judgements(client: TestClient, use_provider) -> None:
    text = json.dumps(analyze(client, use_provider, n=300)).lower()
    for word in ("overbought", "oversold", "bullish", "bearish", "recommend", " buy ", " sell "):
        assert word not in text


def test_phase6_price_data_is_never_modified(client: TestClient, use_provider) -> None:
    market = fetch_market(client, use_provider, random_walk_bars(100))
    path = market_storage.market_directory() / Path(market["bars_storage_key"]).name
    before = path.read_bytes()
    client.post("/api/technical/IBM")
    assert path.read_bytes() == before


# ---------------------------------------------------------------------------
# API — reading results
# ---------------------------------------------------------------------------


def test_series_endpoint_returns_recent_rows_in_order_with_nulls_for_warmup(client: TestClient, use_provider) -> None:
    analyze(client, use_provider, n=300)
    body = client.get("/api/technical/ibm/series?limit=300").json()
    assert body["total_rows"] == 300 and body["returned_rows"] == 300
    rows = body["rows"]
    assert [r["date"] for r in rows] == sorted(r["date"] for r in rows)
    assert rows[0]["sma_200"] is None and rows[198]["sma_200"] is None and rows[199]["sma_200"] is not None
    assert rows[0]["sma_20"] is None and rows[19]["sma_20"] is not None
    assert all(type(rows[-1][k]) is float for k in rows[-1] if k != "date")

    recent = client.get("/api/technical/IBM/series?limit=3").json()
    assert recent["returned_rows"] == 3 and recent["rows"] == rows[-3:]
    assert client.get("/api/technical/IBM/series").json()["returned_rows"] == 100  # default limit


@pytest.mark.parametrize("limit", [0, 1001, "abc"])
def test_series_limit_is_validated(client: TestClient, use_provider, limit) -> None:
    analyze(client, use_provider, n=100)
    response = client.get(f"/api/technical/IBM/series?limit={limit}")
    assert response.status_code == 422 and response.json()["detail"]["code"] == "INVALID_REQUEST"


def test_get_and_series_before_any_analysis_return_404(client: TestClient, use_provider) -> None:
    fetch_market(client, use_provider, random_walk_bars(100))
    result = client.get("/api/technical/IBM")
    assert result.status_code == 404 and result.json()["detail"]["code"] == "TECHNICAL_RESULT_NOT_FOUND"
    series = client.get("/api/technical/IBM/series")
    assert series.status_code == 404 and series.json()["detail"]["code"] == "TECHNICAL_SERIES_NOT_FOUND"


def test_series_comes_from_the_latest_successful_run_not_a_later_failed_one(client: TestClient, use_provider) -> None:
    good = analyze(client, use_provider, n=100)
    fetch_market(client, use_provider, random_walk_bars(5, seed=2))  # too short -> FAILED run
    failed = client.post("/api/technical/IBM").json()
    assert failed["status"] == "FAILED"
    assert client.get("/api/technical/IBM").json()["id"] == failed["id"]
    assert client.get("/api/technical/IBM/series").json()["result_id"] == good["id"]


def test_series_reports_unavailable_when_the_stored_file_is_gone(client: TestClient, use_provider) -> None:
    analyze(client, use_provider, n=100)
    for path in analysis_storage.analysis_directory().iterdir():
        path.unlink()
    response = client.get("/api/technical/IBM/series")
    assert response.status_code == 404 and response.json()["detail"]["code"] == "TECHNICAL_DATA_UNAVAILABLE"


# ---------------------------------------------------------------------------
# API — invalid input and missing prerequisites
# ---------------------------------------------------------------------------


def test_analysis_without_market_data_returns_404(client: TestClient) -> None:
    response = client.post("/api/technical/IBM")
    assert response.status_code == 404 and response.json()["detail"]["code"] == "MARKET_DATA_NOT_FOUND"


def test_a_symbol_with_only_failed_market_fetches_returns_404(client: TestClient, use_provider) -> None:
    use_provider(FakeProvider(error=ProviderError("PROVIDER_TIMEOUT", "Slow.")))
    client.post("/api/market-data/IBM")
    response = client.post("/api/technical/IBM")
    assert response.status_code == 404 and response.json()["detail"]["code"] == "MARKET_DATA_NOT_FOUND"


@pytest.mark.parametrize("symbol", ["A%20B", "-AAPL", "TOOLONGSYMBOL", "AAP%24", "AA%3BDROP"])
def test_invalid_symbols_are_rejected_everywhere(client: TestClient, symbol) -> None:
    for call in (client.post(f"/api/technical/{symbol}"), client.get(f"/api/technical/{symbol}"),
                 client.get(f"/api/technical/{symbol}/series")):
        assert call.status_code == 400 and call.json()["detail"]["code"] == "INVALID_SYMBOL"


# ---------------------------------------------------------------------------
# Failure handling — a COMPLETE result always has its file; nothing orphaned
# ---------------------------------------------------------------------------


def test_missing_market_file_fails_the_run_cleanly(client: TestClient, use_provider) -> None:
    fetch_market(client, use_provider, random_walk_bars(100))
    for path in market_storage.market_directory().iterdir():
        path.unlink()
    body = client.post("/api/technical/IBM").json()
    assert body["status"] == "FAILED" and body["error_code"] == "MARKET_DATA_UNAVAILABLE"
    assert analysis_files() == []


def test_unexpected_computation_error_fails_without_leaking(client: TestClient, use_provider, monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    fetch_market(client, use_provider, random_walk_bars(100))

    def exploding(_bars):
        raise RuntimeError("boom internal detail /srv/secret/path")

    monkeypatch.setattr(technical_report, "build_report", exploding)
    response = client.post("/api/technical/IBM")
    body = response.json()
    assert body["status"] == "FAILED" and body["error_code"] == "TECHNICAL_ANALYSIS_FAILURE"
    assert "boom" not in response.text and "/srv/secret" not in response.text
    assert "boom" not in caplog.text, "only the exception type may be logged"
    assert analysis_files() == []


def test_storage_failure_fails_the_run_and_keeps_nothing(client: TestClient, use_provider, monkeypatch) -> None:
    fetch_market(client, use_provider, random_walk_bars(100))

    def failing_save(_csv):
        raise AnalysisRequestError("ANALYSIS_STORAGE_FAILURE", "x", status_code=500)

    monkeypatch.setattr(analysis_storage, "save_metrics_csv", failing_save)
    body = client.post("/api/technical/IBM").json()
    assert body["status"] == "FAILED" and body["error_code"] == "ANALYSIS_STORAGE_FAILURE"
    assert body["indicators"] == [] and body["indicators_storage_key"] is None
    assert analysis_files() == []


def test_partial_write_is_removed_and_run_fails(client: TestClient, use_provider, monkeypatch) -> None:
    fetch_market(client, use_provider, random_walk_bars(100))
    real_open = Path.open

    class HalfWriteHandle:
        def __init__(self, handle):
            self._handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            self._handle.close()
            return False

        def write(self, data):
            self._handle.write(data[:4])
            self._handle.flush()
            raise OSError("No space left on device")

    def open_with_failing_writes(self, mode="r", *args, **kwargs):
        handle = real_open(self, mode, *args, **kwargs)
        return HalfWriteHandle(handle) if mode == "x" else handle

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", open_with_failing_writes)
        body = client.post("/api/technical/IBM").json()

    assert body["status"] == "FAILED" and body["error_code"] == "ANALYSIS_STORAGE_FAILURE"
    assert "No space left" not in json.dumps(body)
    assert analysis_files() == []


def test_database_failure_removes_the_stored_series(client: TestClient, use_provider, monkeypatch) -> None:
    fetch_market(client, use_provider, random_walk_bars(100))
    db = database.SessionLocal()
    try:
        def failing_commit():
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(db, "commit", failing_commit)
        with pytest.raises(RuntimeError):
            technical_service.analyze_technical(db, "IBM")
    finally:
        db.close()

    assert analysis_files() == []
    check = database.SessionLocal()
    try:
        assert check.query(TechnicalAnalysisResult).count() == 0
    finally:
        check.close()
