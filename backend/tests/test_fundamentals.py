"""Phase 5 — fundamental analysis tests.

Verifies the arithmetic against hand-computed values, the honesty rules
(denominators must be > 0, no substituting one concept for another, no
silent de-duplication or reordering, every skip explained), the API
contract, and the all-or-nothing storage guarantees. Nothing here judges
whether a ratio is good or bad — Phase 5 only computes and explains.
"""

import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import database
from app.core.exceptions import AnalysisRequestError
from app.services import (
    analysis_storage,
    file_processing,
    file_service,
    fundamental_metrics,
    fundamental_service,
)

# Reuse Phase 2's helpers rather than duplicating them.
from tests.test_processing import XLSX_MIME, big_upload_limit, build_xlsx  # noqa: F401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def upload_csv(client: TestClient, text: str, name: str = "data.csv") -> str:
    response = client.post("/api/files", files={"file": (name, text.encode(), "text/csv")})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def process(client: TestClient, file_id: str) -> dict:
    response = client.post(f"/api/files/{file_id}/process")
    assert response.status_code == 201, response.text
    return response.json()


def analyze_csv(client: TestClient, text: str) -> tuple[str, dict]:
    """Upload + process + analyze a CSV. Returns (file_id, first worksheet analysis)."""
    file_id = upload_csv(client, text)
    process(client, file_id)
    response = client.post(f"/api/files/{file_id}/fundamentals")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "COMPLETE", body
    return file_id, body["worksheets"][0]


def metrics_by_key(sheet: dict) -> dict[str, dict]:
    return {m["key"]: m for m in sheet["metrics"]}


def read_artifact(sheet: dict) -> list[dict]:
    path = analysis_storage.analysis_directory() / Path(sheet["metrics_storage_key"]).name
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))


def analysis_files() -> list[str]:
    return sorted(p.name for p in analysis_storage.analysis_directory().iterdir())


def artifact_value(row: dict, key: str) -> float | None:
    return float(row[key]) if row[key] != "" else None


FULL_HEADER = "Date,Company,Revenue,Net Income,Profit,Expenses,Assets,Liabilities,Equity,Debt,Price,EPS"


# ---------------------------------------------------------------------------
# Arithmetic and explainability
# ---------------------------------------------------------------------------


def test_all_ratios_match_hand_computed_values(client: TestClient) -> None:
    text = f"{FULL_HEADER}\n2024-01-01,Acme,1000,150,300,700,2000,800,1200,400,30,3\n"
    _, sheet = analyze_csv(client, text)
    assert sheet["status"] == "ANALYZED"
    row = read_artifact(sheet)[0]
    expected = {
        "net_profit_margin": 150 / 1000,
        "profit_margin": 300 / 1000,
        "expense_ratio": 700 / 1000,
        "return_on_assets": 150 / 2000,
        "return_on_equity": 150 / 1200,
        "debt_to_equity": 400 / 1200,
        "liabilities_to_assets": 800 / 2000,
        "equity_ratio": 1200 / 2000,
        "price_to_earnings": 30 / 3,
    }
    for key, value in expected.items():
        assert artifact_value(row, key) == pytest.approx(value), key
    assert sheet["entity_column"] == "company"


def test_each_metric_reports_formula_inputs_and_counts(client: TestClient) -> None:
    text = "Revenue,Net Income\n1000,100\n2000,300\n"
    _, sheet = analyze_csv(client, text)
    margin = metrics_by_key(sheet)["net_profit_margin"]
    assert margin["status"] == "COMPUTED"
    assert margin["formula"] == "net_income / revenue"
    assert margin["inputs"] == ["net_income", "revenue"]
    assert margin["computed_count"] == 2
    assert margin["skipped_count"] == 0
    assert margin["min"] == pytest.approx(0.1)
    assert margin["max"] == pytest.approx(0.15)
    assert margin["mean"] == pytest.approx(0.125)


def test_skip_reasons_are_counted_per_cause(client: TestClient) -> None:
    text = "Revenue,Net Income\n100,10\n,10\nn/a,10\n0,10\n-5,10\n"
    _, sheet = analyze_csv(client, text)
    margin = metrics_by_key(sheet)["net_profit_margin"]
    assert margin["computed_count"] == 1
    assert margin["skipped_count"] == 4
    assert margin["skipped_reasons"] == {
        "missing revenue": 1,
        "non-numeric revenue": 1,
        "non-positive revenue": 2,
    }


def test_currency_and_percent_formatting_is_parsed_but_parentheses_are_not_guessed(client: TestClient) -> None:
    text = 'Revenue,Net Income\n"$1,000",150\n"(1,000)",150\n'
    _, sheet = analyze_csv(client, text)
    margin = metrics_by_key(sheet)["net_profit_margin"]
    assert margin["computed_count"] == 1
    assert margin["min"] == pytest.approx(0.15)
    # "(1,000)" is NOT silently read as -1000: it is reported as non-numeric.
    assert margin["skipped_reasons"] == {"non-numeric revenue": 1}


def test_negative_equity_skips_equity_ratios_instead_of_returning_negative_values(client: TestClient) -> None:
    text = "Net Income,Debt,Equity\n50,100,-200\n50,100,200\n"
    _, sheet = analyze_csv(client, text)
    metrics = metrics_by_key(sheet)
    for key in ("return_on_equity", "debt_to_equity"):
        assert metrics[key]["computed_count"] == 1
        assert metrics[key]["skipped_reasons"] == {"non-positive equity": 1}
    rows = read_artifact(sheet)
    assert artifact_value(rows[0], "return_on_equity") is None
    assert artifact_value(rows[1], "return_on_equity") == pytest.approx(0.25)


def test_price_to_earnings_skips_non_positive_eps(client: TestClient) -> None:
    text = "Price,EPS\n50,2\n50,0\n50,-1\n"
    _, sheet = analyze_csv(client, text)
    pe = metrics_by_key(sheet)["price_to_earnings"]
    assert pe["computed_count"] == 1
    assert pe["skipped_reasons"] == {"non-positive eps": 2}
    assert pe["min"] == pytest.approx(25.0)


def test_duplicate_rows_are_not_deduplicated(client: TestClient) -> None:
    text = "Revenue,Net Income\n100,10\n100,10\n"
    _, sheet = analyze_csv(client, text)
    assert metrics_by_key(sheet)["net_profit_margin"]["computed_count"] == 2
    assert len(read_artifact(sheet)) == 2


def test_artifact_keeps_file_order_and_row_count(client: TestClient) -> None:
    text = "Date,Revenue,Net Income\n2024-03-01,300,30\n2024-01-01,100,10\n2024-02-01,200,20\n"
    _, sheet = analyze_csv(client, text)
    rows = read_artifact(sheet)
    assert [r["row_index"] for r in rows] == ["0", "1", "2"]
    assert [r["date"] for r in rows] == ["2024-03-01", "2024-01-01", "2024-02-01"]  # not re-sorted
    assert sheet["row_count"] == 3
    assert len(sheet["preview_rows"]) == 3


# ---------------------------------------------------------------------------
# Not computable / skipped worksheets — always with a reason
# ---------------------------------------------------------------------------


def test_metric_not_computable_when_input_column_missing(client: TestClient) -> None:
    _, sheet = analyze_csv(client, "Revenue,Net Income\n100,10\n")
    roe = metrics_by_key(sheet)["return_on_equity"]
    assert roe["status"] == "NOT_COMPUTABLE"
    assert "equity column not found" in roe["reason"]
    assert roe["computed_count"] == 0


def test_sales_is_not_assumed_to_be_revenue(client: TestClient) -> None:
    _, sheet = analyze_csv(client, "Sales,Net Income\n1000,100\n")
    margin = metrics_by_key(sheet)["net_profit_margin"]
    assert margin["status"] == "NOT_COMPUTABLE"
    assert "revenue column not found" in margin["reason"]
    assert "'sales' column exists but is not assumed to be equivalent" in margin["reason"]


def test_profit_is_not_assumed_to_be_net_income(client: TestClient) -> None:
    _, sheet = analyze_csv(client, "Revenue,Profit\n1000,100\n")
    metrics = metrics_by_key(sheet)
    assert metrics["net_profit_margin"]["status"] == "NOT_COMPUTABLE"
    assert metrics["profit_margin"]["status"] == "COMPUTED"  # profit is used only as profit


def test_ambiguous_columns_make_a_metric_not_computable_and_say_so(client: TestClient) -> None:
    _, sheet = analyze_csv(client, "Revenue,Total Revenue,Net Income\n1000,1000,100\n")
    margin = metrics_by_key(sheet)["net_profit_margin"]
    assert margin["status"] == "NOT_COMPUTABLE"
    assert "revenue is ambiguous" in margin["reason"]
    assert "Revenue" in margin["reason"] and "Total Revenue" in margin["reason"]


def test_worksheet_with_no_recognized_financial_columns_is_skipped(client: TestClient) -> None:
    file_id = upload_csv(client, "Foo,Bar\n1,2\n")
    process(client, file_id)
    body = client.post(f"/api/files/{file_id}/fundamentals").json()
    sheet = body["worksheets"][0]
    assert body["status"] == "COMPLETE"
    assert sheet["status"] == "SKIPPED"
    assert "No recognized financial columns" in sheet["reason"]
    assert sheet["metrics_storage_key"] is None
    assert analysis_files() == []


def test_worksheet_where_no_metric_can_be_computed_is_skipped_without_artifact(client: TestClient) -> None:
    file_id = upload_csv(client, "Revenue,Cash\n100,5\n")  # revenue alone pairs with nothing; no date for growth
    process(client, file_id)
    sheet = client.post(f"/api/files/{file_id}/fundamentals").json()["worksheets"][0]
    assert sheet["status"] == "SKIPPED"
    assert "No metric could be computed" in sheet["reason"]
    assert all(m["status"] == "NOT_COMPUTABLE" for m in sheet["metrics"])
    assert analysis_files() == []


# ---------------------------------------------------------------------------
# Growth: ordered by date within each entity, never by file order
# ---------------------------------------------------------------------------


def test_growth_is_computed_in_date_order_not_file_order(client: TestClient) -> None:
    text = "Date,Revenue\n2024-03-01,150\n2024-01-01,100\n2024-02-01,120\n"
    _, sheet = analyze_csv(client, text)
    rows = read_artifact(sheet)
    growth = [artifact_value(r, "revenue_growth") for r in rows]
    assert growth[0] == pytest.approx((150 - 120) / 120)  # March vs February
    assert growth[1] is None  # January is the first period
    assert growth[2] == pytest.approx((120 - 100) / 100)  # February vs January
    assert metrics_by_key(sheet)["revenue_growth"]["skipped_reasons"] == {"no prior period": 1}


def test_growth_is_computed_per_entity_never_across_entities(client: TestClient) -> None:
    text = (
        "Date,Ticker,Revenue\n"
        "2024-01-01,AAA,100\n2024-01-01,BBB,10\n2024-02-01,AAA,200\n2024-02-01,BBB,15\n"
    )
    _, sheet = analyze_csv(client, text)
    assert sheet["entity_column"] == "ticker"
    rows = read_artifact(sheet)
    assert artifact_value(rows[2], "revenue_growth") == pytest.approx(1.0)  # AAA 100 -> 200
    assert artifact_value(rows[3], "revenue_growth") == pytest.approx(0.5)  # BBB 10 -> 15
    assert metrics_by_key(sheet)["revenue_growth"]["skipped_reasons"] == {"no prior period": 2}


def test_growth_skips_duplicate_periods_and_warns(client: TestClient) -> None:
    text = "Date,Revenue\n2024-01-01,100\n2024-01-01,110\n2024-02-01,200\n"
    _, sheet = analyze_csv(client, text)
    growth = metrics_by_key(sheet)["revenue_growth"]
    assert growth["skipped_reasons"]["duplicate period"] == 2
    assert any("share the same period" in w for w in sheet["warnings"])
    rows = read_artifact(sheet)
    assert [artifact_value(r, "revenue_growth") for r in rows] == [None, None, None]


def test_growth_skips_invalid_dates(client: TestClient) -> None:
    text = "Date,Revenue\n2024-01-01,100\nnot a date,150\n2024-02-01,200\n"
    _, sheet = analyze_csv(client, text)
    growth = metrics_by_key(sheet)["revenue_growth"]
    assert growth["skipped_reasons"]["invalid date"] == 1
    assert growth["computed_count"] == 1
    assert growth["max"] == pytest.approx(1.0)  # Jan -> Feb, the unparseable row is ignored


def test_growth_skips_when_prior_value_is_not_positive(client: TestClient) -> None:
    text = "Date,Revenue\n2024-01-01,0\n2024-02-01,100\n"
    _, sheet = analyze_csv(client, text)
    assert metrics_by_key(sheet)["revenue_growth"]["skipped_reasons"]["non-positive prior revenue"] == 1


def test_growth_not_computable_without_a_date_column(client: TestClient) -> None:
    _, sheet = analyze_csv(client, "Revenue,Net Income\n100,10\n")
    growth = metrics_by_key(sheet)["revenue_growth"]
    assert growth["status"] == "NOT_COMPUTABLE"
    assert "date column not found" in growth["reason"]


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_parse_numeric_column_states() -> None:
    import pandas as pd

    series = pd.Series(["$1,200", "5%", "", None, "abc", "(300)", "inf", "1_000"])
    values, states = fundamental_metrics.parse_numeric_column(series)
    assert states == ["ok", "ok", "missing", "missing", "non-numeric", "non-numeric", "non-numeric", "non-numeric"]
    assert values[:2] == [1200.0, 5.0]
    assert all(isinstance(v, float) or v is None for v in values)  # native floats, JSON-safe


# ---------------------------------------------------------------------------
# Multi-sheet workbooks, missing artifacts, failed processing
# ---------------------------------------------------------------------------


def test_multi_sheet_workbook_with_empty_sheet(client: TestClient, big_upload_limit) -> None:
    content = build_xlsx({
        "Financials": [["Revenue", "Net Income"], [1000, 100]],
        "Notes": [],
    })
    upload = client.post("/api/files", files={"file": ("book.xlsx", content, XLSX_MIME)})
    file_id = upload.json()["id"]
    process(client, file_id)
    body = client.post(f"/api/files/{file_id}/fundamentals").json()
    by_name = {s["sheet_name"]: s for s in body["worksheets"]}
    assert by_name["Financials"]["status"] == "ANALYZED"
    assert by_name["Financials"]["metrics_storage_key"].startswith("analysis/")
    assert by_name["Notes"]["status"] == "SKIPPED"
    assert "no data" in by_name["Notes"]["reason"]


def test_sheet_is_skipped_when_phase2_cleaned_file_is_gone(client: TestClient) -> None:
    file_id = upload_csv(client, "Revenue,Net Income\n100,10\n")
    process(client, file_id)
    for path in file_processing.exports_directory().iterdir():
        path.unlink()
    body = client.post(f"/api/files/{file_id}/fundamentals").json()
    assert body["status"] == "COMPLETE"
    assert body["worksheets"][0]["status"] == "SKIPPED"
    assert "could not be read" in body["worksheets"][0]["reason"]


def test_failed_processing_run_yields_failed_analysis(client: TestClient) -> None:
    # Not valid UTF-8, so Phase 2 cannot read it and records FAILED.
    bad = client.post("/api/files", files={"file": ("bad.csv", b"a,b\n\xff\xfe,2\n", "text/csv")})
    file_id = bad.json()["id"]
    assert process(client, file_id)["status"] == "FAILED"

    response = client.post(f"/api/files/{file_id}/fundamentals")
    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "FAILED"
    assert body["worksheets"] == []
    assert "did not complete" in body["error_message"]


# ---------------------------------------------------------------------------
# API contract
# ---------------------------------------------------------------------------


def test_analysis_before_processing_returns_404(client: TestClient) -> None:
    file_id = upload_csv(client, "Revenue,Net Income\n100,10\n")
    response = client.post(f"/api/files/{file_id}/fundamentals")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROCESSING_RESULT_NOT_FOUND"


def test_analysis_file_not_found_returns_404(client: TestClient) -> None:
    response = client.post("/api/files/00000000-0000-0000-0000-000000000000/fundamentals")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "FILE_NOT_FOUND"


def test_analysis_rejects_pdf_files(client: TestClient) -> None:
    upload = client.post("/api/files", files={"file": ("doc.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")})
    response = client.post(f"/api/files/{upload.json()['id']}/fundamentals")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_get_before_any_analysis_returns_404(client: TestClient) -> None:
    file_id = upload_csv(client, "Revenue,Net Income\n100,10\n")
    response = client.get(f"/api/files/{file_id}/fundamentals")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "FUNDAMENTAL_RESULT_NOT_FOUND"


def test_get_returns_latest_and_result_records_which_processing_run_it_used(client: TestClient) -> None:
    file_id = upload_csv(client, "Revenue,Net Income\n100,10\n")
    first_processing = process(client, file_id)
    first = client.post(f"/api/files/{file_id}/fundamentals").json()
    assert first["processing_result_id"] == first_processing["id"]

    second_processing = process(client, file_id)  # re-process: a newer run exists now
    second = client.post(f"/api/files/{file_id}/fundamentals").json()
    assert second["processing_result_id"] == second_processing["id"]
    assert first["processing_result_id"] != second["processing_result_id"]

    latest = client.get(f"/api/files/{file_id}/fundamentals").json()
    assert latest["id"] == second["id"]


def test_original_upload_and_phase2_cleaned_data_are_never_modified(client: TestClient) -> None:
    text = "Revenue,Net Income\n100,10\n"
    upload = client.post("/api/files", files={"file": ("keep.csv", text.encode(), "text/csv")})
    file_id, stored = upload.json()["id"], upload.json()["stored_filename"]
    process(client, file_id)

    from app.services import file_storage

    cleaned_before = {p.name: p.read_bytes() for p in file_processing.exports_directory().iterdir()}
    client.post(f"/api/files/{file_id}/fundamentals")

    assert (file_storage.upload_directory() / stored).read_bytes() == text.encode()
    cleaned_after = {p.name: p.read_bytes() for p in file_processing.exports_directory().iterdir()}
    assert cleaned_after == cleaned_before


# ---------------------------------------------------------------------------
# Storage failures — all-or-nothing, same rule as Phase 4
# ---------------------------------------------------------------------------


def _two_sheet_workbook_ready(client: TestClient) -> str:
    content = build_xlsx({
        "One": [["Revenue", "Net Income"], [1000, 100]],
        "Two": [["Revenue", "Net Income"], [2000, 300]],
    })
    upload = client.post("/api/files", files={"file": ("two.xlsx", content, XLSX_MIME)})
    file_id = upload.json()["id"]
    process(client, file_id)
    return file_id


def test_storage_failure_on_later_sheet_fails_run_and_rolls_back_earlier_artifacts(
    client: TestClient, monkeypatch, big_upload_limit
) -> None:
    file_id = _two_sheet_workbook_ready(client)
    real_save = analysis_storage.save_metrics_csv
    saved: list[str] = []

    def flaky_save(csv_text):
        if saved:  # first sheet saved fine; second fails
            raise AnalysisRequestError("ANALYSIS_STORAGE_FAILURE", "x", status_code=500)
        result = real_save(csv_text)
        saved.append(result[1])
        return result

    monkeypatch.setattr(analysis_storage, "save_metrics_csv", flaky_save)
    response = client.post(f"/api/files/{file_id}/fundamentals")
    body = response.json()

    assert response.status_code == 201
    assert body["status"] == "FAILED"
    assert body["worksheets"] == []
    assert "ANALYSIS_STORAGE_FAILURE" in body["error_message"]
    assert "worksheet #2" in body["error_message"]
    assert len(saved) == 1, "the first worksheet's artifact was really written"
    assert analysis_files() == [], "...and rolled back"


def test_partial_write_is_removed_and_run_fails(client: TestClient, monkeypatch) -> None:
    file_id = upload_csv(client, "Revenue,Net Income\n100,10\n")
    process(client, file_id)
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
        response = client.post(f"/api/files/{file_id}/fundamentals")

    body = response.json()
    assert body["status"] == "FAILED"
    assert body["worksheets"] == []
    assert "No space left" not in body["error_message"]
    assert analysis_files() == []


def test_unexpected_failure_rolls_back_and_does_not_leak(client: TestClient, monkeypatch, big_upload_limit) -> None:
    file_id = _two_sheet_workbook_ready(client)
    real_analyze = fundamental_metrics.analyze_sheet
    calls = {"n": 0}

    def exploding(df, ambiguous):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom internal detail")
        return real_analyze(df, ambiguous)

    monkeypatch.setattr(fundamental_metrics, "analyze_sheet", exploding)
    body = client.post(f"/api/files/{file_id}/fundamentals").json()
    assert body["status"] == "FAILED"
    assert body["worksheets"] == []
    assert "worksheet #2" in body["error_message"]
    assert "boom" not in body["error_message"]
    assert analysis_files() == []


def test_database_failure_after_artifacts_written_removes_them(client: TestClient, monkeypatch) -> None:
    file_id = upload_csv(client, "Revenue,Net Income\n100,10\n")
    process(client, file_id)

    db = database.SessionLocal()
    try:
        record = file_service.get_file(db, file_id)

        def failing_commit():
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(db, "commit", failing_commit)
        with pytest.raises(RuntimeError):
            fundamental_service.analyze_fundamentals(db, record)
    finally:
        db.close()

    assert analysis_files() == []
    check = database.SessionLocal()
    try:
        assert fundamental_service.get_latest_result(check, file_id) is None
    finally:
        check.close()


def test_delete_artifacts_never_raises_and_cannot_escape_the_directory(monkeypatch, tmp_path) -> None:
    _, key = analysis_storage.save_metrics_csv("a,b\n1,2\n")
    with monkeypatch.context() as patch:
        def failing_unlink(self, *args, **kwargs):
            raise OSError("permission denied")

        patch.setattr(Path, "unlink", failing_unlink)
        assert analysis_storage.delete_artifacts([key]) == [key]
    assert analysis_storage.delete_artifacts([key]) == []
    assert analysis_files() == []

    outside = tmp_path / "outside.txt"
    outside.write_text("must survive")
    analysis_storage.delete_artifacts([f"../{outside.name}", str(outside)])
    assert outside.read_text() == "must survive"
