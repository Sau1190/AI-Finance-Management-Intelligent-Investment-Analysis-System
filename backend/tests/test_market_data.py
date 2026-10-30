"""Phase 6 — market data adapter tests.

No test touches the network. The Alpha Vantage adapter is exercised through
httpx.MockTransport using the vendor's documented response shape, and the API
is exercised with a fake provider injected through FastAPI's dependency
overrides. Live-provider behaviour is therefore verified only against that
documented shape, not against the real service.
"""

import json
import logging
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.routes.market_data import get_market_provider
from app.core import database
from app.core.config import get_settings
from app.core.exceptions import MarketDataRequestError
from app.main import app
from app.models.market_data_snapshot import MarketDataSnapshot
from app.services import market_service, market_storage, market_validation
from app.services.market_providers import (
    MAX_RESPONSE_BYTES,
    AlphaVantageProvider,
    ProviderError,
    build_provider,
)

KEY = "TESTKEY-SECRET-12345"
TODAY = date(2024, 6, 1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def raw_bar(day="2024-01-02", o="100", h="102", l="99", c="101", v="1000") -> dict:
    return {"date": day, "open": o, "high": h, "low": l, "close": c, "volume": v}


def av_row(o="100", h="102", l="99", c="101", v="1000") -> dict:
    return {"1. open": o, "2. high": h, "3. low": l, "4. close": c, "5. volume": v}


def av_payload(rows: dict) -> dict:
    return {"Meta Data": {"2. Symbol": "IBM"}, "Time Series (Daily)": rows}


GOOD_BARS = [
    raw_bar("2024-01-03", "101", "103.5", "100.2", "102.8", "1200000"),
    raw_bar("2024-01-02", "100", "102", "99.5", "101", "900000"),
    raw_bar("2024-01-04", "102.8", "104", "102", "103", "800000"),
]


class FakeProvider:
    name = "fake"

    def __init__(self, bars=None, error: Exception | None = None):
        self.bars = bars if bars is not None else GOOD_BARS
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def fetch_daily(self, symbol: str, history: str) -> list[dict]:
        self.calls.append((symbol, history))
        if self.error is not None:
            raise self.error
        return self.bars


def assert_no_underlying_exception_reachable(error: Exception) -> None:
    """The original httpx/parsing exception (whose text can embed the request
    URL, and so the API key) must not be reachable from the raised error:
    either there never was one, or it was explicitly suppressed (`from None`).
    """
    assert error.__cause__ is None
    assert error.__context__ is None or error.__suppress_context__


def alpha_vantage(handler, key: str = KEY) -> AlphaVantageProvider:
    return AlphaVantageProvider(key, transport=httpx.MockTransport(handler))


@pytest.fixture
def use_provider():
    def install(provider):
        app.dependency_overrides[get_market_provider] = lambda: provider
        return provider

    yield install
    app.dependency_overrides.pop(get_market_provider, None)


def market_files() -> list[str]:
    return sorted(p.name for p in market_storage.market_directory().iterdir())


def all_snapshots() -> list[MarketDataSnapshot]:
    db = database.SessionLocal()
    try:
        return db.query(MarketDataSnapshot).all()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Alpha Vantage adapter (simulated transport, documented response shape)
# ---------------------------------------------------------------------------


def test_adapter_sends_expected_request_and_returns_raw_bars() -> None:
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=av_payload({"2024-01-02": av_row("100", "102", "99", "101", "1000")}))

    provider = alpha_vantage(handler)
    bars = provider.fetch_daily("IBM", "compact")

    params = dict(seen[0].url.params)
    assert seen[0].url.host == "www.alphavantage.co"
    assert params == {
        "function": "TIME_SERIES_DAILY",
        "symbol": "IBM",
        "outputsize": "compact",
        "datatype": "json",
        "apikey": KEY,
    }
    assert bars == [{"date": "2024-01-02", "open": "100", "high": "102", "low": "99", "close": "101", "volume": "1000"}]


def test_adapter_requests_full_history_when_asked() -> None:
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=av_payload({}))

    assert alpha_vantage(handler).fetch_daily("IBM", "full") == []
    assert seen[0]["outputsize"] == "full"


@pytest.mark.parametrize(
    "response, code",
    [
        (httpx.Response(200, json={"Error Message": "Invalid API call ... apikey=" + KEY}), "PROVIDER_REJECTED_REQUEST"),
        (httpx.Response(200, json={"Note": "Thank you for using Alpha Vantage! 25 requests per day"}), "PROVIDER_DECLINED_REQUEST"),
        (httpx.Response(200, json={"Information": "premium endpoint"}), "PROVIDER_DECLINED_REQUEST"),
        (httpx.Response(503, text="down"), "PROVIDER_HTTP_ERROR"),
        (httpx.Response(302, headers={"location": "https://evil.example/?x=1"}), "PROVIDER_HTTP_ERROR"),
        (httpx.Response(200, text="<html>not json</html>"), "PROVIDER_BAD_RESPONSE"),
        (httpx.Response(200, json=[1, 2, 3]), "PROVIDER_BAD_RESPONSE"),
        (httpx.Response(200, json={"Meta Data": {}}), "PROVIDER_BAD_RESPONSE"),
        (httpx.Response(200, json={"Time Series (Daily)": "nope"}), "PROVIDER_BAD_RESPONSE"),
    ],
)
def test_adapter_maps_failures_to_safe_provider_errors(response, code) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return response

    with pytest.raises(ProviderError) as excinfo:
        alpha_vantage(handler).fetch_daily("IBM", "compact")
    error = excinfo.value
    assert error.code == code
    assert len(calls) == 1, "redirects must not be followed"
    # Nothing vendor-supplied, nothing URL-like, and never the key.
    assert KEY not in error.message and KEY not in str(error)
    assert "http" not in error.message.lower() or "HTTP " in error.message
    assert_no_underlying_exception_reachable(error)


@pytest.mark.parametrize(
    "raised, code",
    [
        (httpx.ConnectError("could not connect to https://www.alphavantage.co/query?apikey=" + KEY), "PROVIDER_UNREACHABLE"),
        (httpx.ReadTimeout("timed out for https://www.alphavantage.co/query?apikey=" + KEY), "PROVIDER_TIMEOUT"),
    ],
)
def test_adapter_network_errors_never_leak_the_key(raised, code) -> None:
    def handler(request):
        raise raised

    with pytest.raises(ProviderError) as excinfo:
        alpha_vantage(handler).fetch_daily("IBM", "compact")
    error = excinfo.value
    assert error.code == code
    assert KEY not in error.message and KEY not in str(error)
    assert_no_underlying_exception_reachable(error)


def test_adapter_rejects_oversized_responses(monkeypatch) -> None:
    monkeypatch.setattr("app.services.market_providers.MAX_RESPONSE_BYTES", 50)

    def handler(request):
        return httpx.Response(200, json=av_payload({"2024-01-02": av_row()}))

    with pytest.raises(ProviderError) as excinfo:
        alpha_vantage(handler).fetch_daily("IBM", "compact")
    assert excinfo.value.code == "PROVIDER_BAD_RESPONSE"
    assert MAX_RESPONSE_BYTES == 10 * 1024 * 1024


def test_adapter_passes_malformed_rows_through_for_validation_to_reject() -> None:
    def handler(request):
        return httpx.Response(200, json=av_payload({"2024-01-02": "garbage"}))

    bars = alpha_vantage(handler).fetch_daily("IBM", "compact")
    assert bars == [{"date": "2024-01-02", "open": None, "high": None, "low": None, "close": None, "volume": None}]
    assert market_validation.validate_bars(bars, TODAY)[0] == []


@pytest.mark.parametrize("key", ["", "   "])
def test_adapter_requires_an_api_key(key) -> None:
    with pytest.raises(ProviderError) as excinfo:
        AlphaVantageProvider(key)
    assert excinfo.value.code == "MARKET_DATA_NOT_CONFIGURED"


def test_build_provider_rejects_unsupported_provider() -> None:
    with pytest.raises(ProviderError) as excinfo:
        build_provider("mystery_vendor", KEY, 10.0)
    assert excinfo.value.code == "MARKET_DATA_NOT_CONFIGURED"
    assert isinstance(build_provider("alpha_vantage", KEY, 10.0), AlphaVantageProvider)


def test_request_logging_never_contains_the_api_key(caplog) -> None:
    # httpx logs the full request URL at INFO, and the URL carries the key.
    caplog.set_level(logging.DEBUG)

    def handler(request):
        return httpx.Response(200, json=av_payload({"2024-01-02": av_row()}))

    alpha_vantage(handler).fetch_daily("IBM", "compact")
    assert KEY not in caplog.text


# ---------------------------------------------------------------------------
# Validation (provider-independent, never repairs a bar)
# ---------------------------------------------------------------------------


def test_valid_bars_are_sorted_and_use_native_types() -> None:
    bars, rejected = market_validation.validate_bars(GOOD_BARS, TODAY)
    assert [b["date"] for b in bars] == ["2024-01-02", "2024-01-03", "2024-01-04"]
    assert rejected == {}
    first = bars[0]
    assert first == {"date": "2024-01-02", "open": 100.0, "high": 102.0, "low": 99.5, "close": 101.0, "volume": 900000}
    assert isinstance(first["open"], float) and isinstance(first["volume"], int)


@pytest.mark.parametrize(
    "bar, reason",
    [
        (raw_bar(day="02/01/2024"), "invalid date"),
        (raw_bar(day="2024-13-45"), "invalid date"),
        (raw_bar(day=None), "invalid date"),
        (raw_bar(day="2999-01-01"), "future date"),
        (raw_bar(o="abc"), "non-numeric open"),
        (raw_bar(h=None), "non-numeric high"),
        (raw_bar(l="inf"), "non-numeric low"),
        (raw_bar(c="nan"), "non-numeric close"),
        (raw_bar(o="0"), "non-positive open"),
        (raw_bar(c="-5"), "non-positive close"),
        (raw_bar(v="-1"), "invalid volume"),
        (raw_bar(v="1000.5"), "invalid volume"),
        (raw_bar(v="lots"), "invalid volume"),
        (raw_bar(v=None), "invalid volume"),
        (raw_bar(h="98", l="99", o="98.5", c="98.6"), "high below low"),
        (raw_bar(o="110"), "open outside high/low range"),
        (raw_bar(c="90"), "close outside high/low range"),
    ],
)
def test_invalid_bars_are_rejected_with_a_reason_not_repaired(bar, reason) -> None:
    bars, rejected = market_validation.validate_bars([bar, raw_bar("2024-02-01")], TODAY)
    assert [b["date"] for b in bars] == ["2024-02-01"]
    assert rejected == {reason: 1}


def test_duplicate_dates_drop_both_bars_rather_than_picking_one() -> None:
    bars, rejected = market_validation.validate_bars(
        [raw_bar("2024-01-02"), raw_bar("2024-01-02", c="100"), raw_bar("2024-01-03")], TODAY
    )
    assert [b["date"] for b in bars] == ["2024-01-03"]
    assert rejected == {"duplicate date": 2}


def test_future_tolerance_is_one_day_for_exchange_local_dates() -> None:
    ok, _ = market_validation.validate_bars([raw_bar("2024-06-02")], TODAY)
    late, rejected = market_validation.validate_bars([raw_bar("2024-06-03")], TODAY)
    assert len(ok) == 1
    assert late == [] and rejected == {"future date": 1}


def test_zero_volume_is_valid() -> None:
    bars, rejected = market_validation.validate_bars([raw_bar(v="0")], TODAY)
    assert len(bars) == 1 and rejected == {}


# ---------------------------------------------------------------------------
# API — successful fetch, reading data back
# ---------------------------------------------------------------------------


def test_fetch_stores_validated_bars_and_reports_the_snapshot(client: TestClient, use_provider) -> None:
    provider = use_provider(FakeProvider())
    response = client.post("/api/market-data/ibm")
    assert response.status_code == 201, response.text
    body = response.json()

    assert provider.calls == [("IBM", "compact")]  # symbol upper-cased, default history
    assert body["status"] == "COMPLETE"
    assert body["symbol"] == "IBM" and body["provider"] == "fake" and body["history"] == "compact"
    assert body["bar_count"] == 3
    assert (body["first_date"], body["last_date"]) == ("2024-01-02", "2024-01-04")
    assert body["rejected_bars"] == {}
    assert body["error_code"] is None
    assert [b["date"] for b in body["preview_bars"]] == ["2024-01-02", "2024-01-03", "2024-01-04"]
    assert body["bars_storage_key"].startswith("market/")

    stored = (market_storage.market_directory() / Path(body["bars_storage_key"]).name).read_text()
    assert stored.splitlines()[0] == "date,open,high,low,close,volume"
    assert len(stored.splitlines()) == 4
    assert market_files() == [Path(body["bars_storage_key"]).name]


def test_preview_is_limited_to_the_five_most_recent_bars(client: TestClient, use_provider) -> None:
    bars = [raw_bar(f"2024-01-{d:02d}") for d in range(1, 11)]
    use_provider(FakeProvider(bars))
    body = client.post("/api/market-data/IBM").json()
    assert body["bar_count"] == 10
    assert [b["date"] for b in body["preview_bars"]] == [f"2024-01-{d:02d}" for d in range(6, 11)]


def test_history_option_is_passed_to_the_provider(client: TestClient, use_provider) -> None:
    provider = use_provider(FakeProvider())
    assert client.post("/api/market-data/IBM?history=full").status_code == 201
    assert provider.calls == [("IBM", "full")]


def test_invalid_history_uses_the_standard_error_envelope(client: TestClient, use_provider) -> None:
    provider = use_provider(FakeProvider())
    response = client.post("/api/market-data/IBM?history=weekly")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_REQUEST"
    assert provider.calls == []


def test_partially_invalid_data_is_complete_with_rejections_counted(client: TestClient, use_provider) -> None:
    bars = GOOD_BARS + [raw_bar("2999-01-01"), raw_bar("2024-02-01", h="1", l="2")]
    use_provider(FakeProvider(bars))
    body = client.post("/api/market-data/IBM").json()
    assert body["status"] == "COMPLETE"
    assert body["bar_count"] == 3
    assert body["rejected_bars"] == {"future date": 1, "high below low": 1}


def test_prices_endpoint_returns_most_recent_bars_in_date_order(client: TestClient, use_provider) -> None:
    bars = [raw_bar(f"2024-01-{d:02d}", c=str(100 + d), h="200") for d in range(1, 8)]
    use_provider(FakeProvider(bars))
    client.post("/api/market-data/IBM")

    body = client.get("/api/market-data/ibm/prices?limit=3").json()
    assert body["symbol"] == "IBM"
    assert body["total_bars"] == 7 and body["returned_bars"] == 3
    assert [b["date"] for b in body["bars"]] == ["2024-01-05", "2024-01-06", "2024-01-07"]
    assert body["bars"][-1]["close"] == 107.0 and isinstance(body["bars"][-1]["volume"], int)
    assert body["provider"] == "fake"

    default = client.get("/api/market-data/IBM/prices").json()
    assert default["returned_bars"] == 7


@pytest.mark.parametrize("limit", [0, 1001, "abc"])
def test_prices_limit_is_validated(client: TestClient, use_provider, limit) -> None:
    use_provider(FakeProvider())
    client.post("/api/market-data/IBM")
    response = client.get(f"/api/market-data/IBM/prices?limit={limit}")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_REQUEST"


def test_latest_snapshot_is_returned_by_get(client: TestClient, use_provider) -> None:
    use_provider(FakeProvider())
    first = client.post("/api/market-data/IBM").json()
    second = client.post("/api/market-data/IBM").json()
    fetched = client.get("/api/market-data/IBM").json()
    assert fetched["id"] == second["id"] and fetched["id"] != first["id"]


def test_market_data_does_not_depend_on_any_uploaded_file(client: TestClient, use_provider) -> None:
    use_provider(FakeProvider())
    assert client.get("/api/files").json()["items"] == []
    assert client.post("/api/market-data/IBM").status_code == 201


# ---------------------------------------------------------------------------
# API — not found / invalid input / configuration
# ---------------------------------------------------------------------------


def test_get_before_any_fetch_returns_404(client: TestClient) -> None:
    for path in ("/api/market-data/IBM", "/api/market-data/IBM/prices"):
        response = client.get(path)
        assert response.status_code == 404
    assert client.get("/api/market-data/IBM").json()["detail"]["code"] == "MARKET_RESULT_NOT_FOUND"
    assert client.get("/api/market-data/IBM/prices").json()["detail"]["code"] == "PRICES_NOT_FOUND"


@pytest.mark.parametrize("symbol", ["A%20B", "-AAPL", "TOOLONGSYMBOL", "AAP%24", "AA%3BDROP", "%2E%2E"])
def test_invalid_symbols_are_rejected_before_any_provider_call(client: TestClient, use_provider, symbol) -> None:
    provider = use_provider(FakeProvider())
    for method in (client.post, client.get):
        response = method(f"/api/market-data/{symbol}")
        assert response.status_code == 400, (symbol, response.text)
        assert response.json()["detail"]["code"] == "INVALID_SYMBOL"
    assert provider.calls == []
    assert market_files() == []


def test_path_like_symbols_never_reach_the_provider(client: TestClient, use_provider) -> None:
    provider = use_provider(FakeProvider())
    response = client.post("/api/market-data/..%2Fetc%2Fpasswd")
    assert response.status_code in (400, 404)
    assert provider.calls == []


@pytest.mark.parametrize("symbol", ["BRK.B", "RDS-A", "a", "T"])
def test_legitimate_ticker_formats_are_accepted(client: TestClient, use_provider, symbol) -> None:
    provider = use_provider(FakeProvider())
    assert client.post(f"/api/market-data/{symbol}").status_code == 201
    assert provider.calls[0][0] == symbol.upper()


def test_unconfigured_provider_returns_503_and_records_nothing(client: TestClient) -> None:
    # conftest blanks ALPHA_VANTAGE_API_KEY, so the real dependency must refuse.
    response = client.post("/api/market-data/IBM")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MARKET_DATA_NOT_CONFIGURED"
    assert all_snapshots() == []
    assert market_files() == []


def test_unsupported_provider_setting_returns_503(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "mystery_vendor")
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", KEY)
    get_settings.cache_clear()
    response = client.post("/api/market-data/IBM")
    assert response.status_code == 503
    assert KEY not in response.text


def test_configured_key_builds_the_alpha_vantage_provider(monkeypatch) -> None:
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", KEY)
    get_settings.cache_clear()
    assert isinstance(get_market_provider(), AlphaVantageProvider)


# ---------------------------------------------------------------------------
# API — provider failures are recorded outcomes, never fabricated data
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code",
    ["PROVIDER_DECLINED_REQUEST", "PROVIDER_REJECTED_REQUEST", "PROVIDER_TIMEOUT", "PROVIDER_UNREACHABLE", "PROVIDER_HTTP_ERROR"],
)
def test_provider_errors_become_failed_snapshots(client: TestClient, use_provider, code) -> None:
    use_provider(FakeProvider(error=ProviderError(code, "A safe message.")))
    response = client.post("/api/market-data/IBM")
    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "FAILED"
    assert body["error_code"] == code and body["error_message"] == "A safe message."
    assert body["bar_count"] == 0 and body["preview_bars"] == [] and body["bars_storage_key"] is None
    assert market_files() == []
    assert client.get("/api/market-data/IBM").json()["status"] == "FAILED"
    assert client.get("/api/market-data/IBM/prices").status_code == 404


def test_empty_provider_response_is_a_failure_not_an_empty_success(client: TestClient, use_provider) -> None:
    use_provider(FakeProvider(bars=[]))
    body = client.post("/api/market-data/IBM").json()
    assert body["status"] == "FAILED" and body["error_code"] == "PROVIDER_NO_DATA"
    assert market_files() == []


def test_all_bars_invalid_fails_and_reports_why(client: TestClient, use_provider) -> None:
    use_provider(FakeProvider(bars=[raw_bar(o="abc"), raw_bar("2999-01-01")]))
    body = client.post("/api/market-data/IBM").json()
    assert body["status"] == "FAILED" and body["error_code"] == "NO_VALID_BARS"
    assert body["rejected_bars"] == {"future date": 1, "non-numeric open": 1}
    assert "2 bars" in body["error_message"]
    assert market_files() == []


def test_unexpected_provider_exception_fails_without_leaking(client: TestClient, use_provider, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    use_provider(FakeProvider(error=RuntimeError(f"boom https://x/query?apikey={KEY}")))
    response = client.post("/api/market-data/IBM")
    body = response.json()
    assert body["status"] == "FAILED" and body["error_code"] == "MARKET_DATA_FAILURE"
    assert KEY not in response.text and "boom" not in response.text
    assert KEY not in caplog.text, "only the exception type may be logged"


def test_failed_fetch_does_not_destroy_the_last_good_data(client: TestClient, use_provider) -> None:
    use_provider(FakeProvider())
    good = client.post("/api/market-data/IBM").json()
    use_provider(FakeProvider(error=ProviderError("PROVIDER_DECLINED_REQUEST", "Try later.")))
    failed = client.post("/api/market-data/IBM").json()

    assert client.get("/api/market-data/IBM").json()["id"] == failed["id"]  # latest attempt
    prices = client.get("/api/market-data/IBM/prices").json()  # latest successful data
    assert prices["snapshot_id"] == good["id"] and prices["returned_bars"] == 3


def test_api_key_never_appears_in_responses_database_or_logs(client: TestClient, use_provider, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    outputs = []

    def server_error(request):
        return httpx.Response(500, text="oops " + str(request.url))

    def network_down(request):
        raise httpx.ConnectError("failed: " + str(request.url))

    def ok(request):
        return httpx.Response(200, json=av_payload({"2024-01-02": av_row()}))

    for handler in (server_error, network_down, ok):
        use_provider(alpha_vantage(handler))
        response = client.post("/api/market-data/IBM")
        assert response.status_code == 201
        outputs.append(response.text)
        outputs.append(client.get("/api/market-data/IBM").text)

    for snapshot in all_snapshots():
        outputs.append(json.dumps({c.name: str(getattr(snapshot, c.name)) for c in snapshot.__table__.columns}))
    assert len(all_snapshots()) == 3
    assert not any(KEY in text for text in outputs)
    assert KEY not in caplog.text
    assert not any(KEY in p.read_text() for p in market_storage.market_directory().iterdir())


# ---------------------------------------------------------------------------
# Storage failures — a COMPLETE snapshot always has its file; nothing orphaned
# ---------------------------------------------------------------------------


def test_storage_failure_fails_the_fetch_and_keeps_nothing(client: TestClient, use_provider, monkeypatch) -> None:
    use_provider(FakeProvider())

    def failing_save(_csv):
        raise MarketDataRequestError("MARKET_STORAGE_FAILURE", "x", status_code=500)

    monkeypatch.setattr(market_storage, "save_bars_csv", failing_save)
    body = client.post("/api/market-data/IBM").json()
    assert body["status"] == "FAILED" and body["error_code"] == "MARKET_STORAGE_FAILURE"
    assert body["bars_storage_key"] is None and body["bar_count"] == 0
    assert market_files() == []


def test_partial_write_is_removed_and_fetch_fails(client: TestClient, use_provider, monkeypatch) -> None:
    use_provider(FakeProvider())
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
        body = client.post("/api/market-data/IBM").json()

    assert body["status"] == "FAILED" and body["error_code"] == "MARKET_STORAGE_FAILURE"
    assert "No space left" not in json.dumps(body)
    assert market_files() == []


def test_database_failure_removes_the_stored_file(client: TestClient, monkeypatch) -> None:
    db = database.SessionLocal()
    try:
        def failing_commit():
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(db, "commit", failing_commit)
        with pytest.raises(RuntimeError):
            market_service.fetch_and_store(db, "IBM", "compact", FakeProvider())
    finally:
        db.close()
    assert market_files() == []
    assert all_snapshots() == []


def test_prices_report_unavailable_when_the_stored_file_is_gone(client: TestClient, use_provider) -> None:
    use_provider(FakeProvider())
    client.post("/api/market-data/IBM")
    for path in market_storage.market_directory().iterdir():
        path.unlink()
    response = client.get("/api/market-data/IBM/prices")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "MARKET_DATA_UNAVAILABLE"


def test_delete_artifacts_never_raises_and_cannot_escape_the_directory(monkeypatch, tmp_path) -> None:
    _, key = market_storage.save_bars_csv("date,open,high,low,close,volume\n")
    with monkeypatch.context() as patch:
        def failing_unlink(self, *args, **kwargs):
            raise OSError("permission denied")

        patch.setattr(Path, "unlink", failing_unlink)
        assert market_storage.delete_artifacts([key]) == [key]
    assert market_storage.delete_artifacts([key]) == []
    assert market_files() == []

    outside = tmp_path / "outside.txt"
    outside.write_text("must survive")
    market_storage.delete_artifacts([f"../{outside.name}", str(outside)])
    assert outside.read_text() == "must survive"
