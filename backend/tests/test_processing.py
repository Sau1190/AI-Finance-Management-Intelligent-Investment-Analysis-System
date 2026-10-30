"""Phase 2 — Excel & CSV processing tests.

Covers header/type/quality detection, financial-column normalization,
XLSX and CSV specific behavior, and security/reliability guarantees
(original file integrity, no crashes on malformed input, consistent
error envelope). No fundamental/market/technical analysis is exercised
here — Phase 2 only produces a validated, explainable data-quality report.
"""

import io

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def big_upload_limit(monkeypatch):
    """conftest's shared MAX_UPLOAD_BYTES=1024 is sized for Phase 1's small
    fixtures; a minimal real XLSX workbook alone is ~5KB. Tests that need to
    upload a realistic workbook request this fixture to raise the ceiling.
    """
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "5000000")
    get_settings.cache_clear()


def build_xlsx(sheets: dict[str, list[list]]) -> bytes:
    """Build a real XLSX workbook from {sheet_name: rows}. An empty rows
    list produces a genuinely empty worksheet.
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def upload_and_process(client: TestClient, filename: str, content: bytes, content_type: str) -> dict:
    upload = client.post("/api/files", files={"file": (filename, content, content_type)})
    assert upload.status_code == 201, upload.text
    file_id = upload.json()["id"]
    response = client.post(f"/api/files/{file_id}/process")
    return response


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------


def test_process_valid_single_sheet_xlsx(client: TestClient, big_upload_limit) -> None:
    content = build_xlsx({"Sheet1": [
        ["Date", "Ticker", "Revenue", "Net Income"],
        ["2024-01-01", "ACME", 5000, 800],
        ["2024-02-01", "ACME", 5200, 850],
    ]})
    response = upload_and_process(client, "report.xlsx", content, XLSX_MIME)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "COMPLETE"
    sheet = body["worksheets"][0]
    assert sheet["row_count"] == 2
    assert sheet["header_row_index"] == 0
    names = {c["name"]: c for c in sheet["columns"]}
    assert names["Revenue"]["inferred_type"] == "integer"
    assert names["Revenue"]["canonical_concept"] == "revenue"
    assert names["Date"]["inferred_type"] == "date"
    assert sheet["cleaned_data_status"] == "GENERATED"
    assert sheet["cleaned_data_storage_key"].startswith("exports/")


def test_process_valid_multi_sheet_xlsx(client: TestClient, big_upload_limit) -> None:
    content = build_xlsx({
        "Q1": [["Date", "Revenue"], ["2024-01-01", 100]],
        "Q2": [["Date", "Revenue"], ["2024-04-01", 200]],
    })
    response = upload_and_process(client, "multi.xlsx", content, XLSX_MIME)
    assert response.status_code == 201
    body = response.json()
    sheet_names = {s["sheet_name"] for s in body["worksheets"]}
    assert sheet_names == {"Q1", "Q2"}
    assert all(s["cleaned_data_status"] == "GENERATED" for s in body["worksheets"])


def test_process_empty_worksheet(client: TestClient, big_upload_limit) -> None:
    content = build_xlsx({"Data": [["Date", "Revenue"], ["2024-01-01", 100]], "Notes": []})
    response = upload_and_process(client, "withnotes.xlsx", content, XLSX_MIME)
    assert response.status_code == 201
    body = response.json()
    notes = next(s for s in body["worksheets"] if s["sheet_name"] == "Notes")
    assert notes["is_empty"] is True
    assert notes["cleaned_data_status"] == "SKIPPED"
    assert any("no data" in w.lower() for w in notes["warnings"])


def test_process_header_not_on_first_row(client: TestClient, big_upload_limit) -> None:
    content = build_xlsx({"Report": [
        ["Quarterly Financial Report - Confidential"],
        ["Date", "Revenue"],
        ["2024-01-01", 100],
        ["2024-02-01", 200],
    ]})
    response = upload_and_process(client, "titled.xlsx", content, XLSX_MIME)
    assert response.status_code == 201
    sheet = response.json()["worksheets"][0]
    assert sheet["header_row_index"] == 1
    assert sheet["header_assumed_default"] is False
    assert sheet["row_count"] == 2


def test_process_mixed_data_types_column(client: TestClient, big_upload_limit) -> None:
    content = build_xlsx({"Sheet1": [
        ["Date", "EPS"],
        ["2024-01-01", 1.2],
        ["2024-02-01", "not a number"],
    ]})
    response = upload_and_process(client, "mixed.xlsx", content, XLSX_MIME)
    assert response.status_code == 201
    eps = next(c for c in response.json()["worksheets"][0]["columns"] if c["name"] == "EPS")
    # Below the 90% conformance threshold -> falls back to "string", not a crash.
    assert eps["inferred_type"] == "string"


def test_process_missing_values_counted(client: TestClient, big_upload_limit) -> None:
    content = build_xlsx({"Sheet1": [
        ["Date", "Revenue"],
        ["2024-01-01", 100],
        ["2024-02-01", None],
        ["2024-03-01", 300],
    ]})
    response = upload_and_process(client, "missing.xlsx", content, XLSX_MIME)
    revenue = next(c for c in response.json()["worksheets"][0]["columns"] if c["name"] == "Revenue")
    assert revenue["missing_count"] == 1


def test_process_duplicate_rows_detected(client: TestClient, big_upload_limit) -> None:
    content = build_xlsx({"Sheet1": [
        ["Date", "Revenue"],
        ["2024-01-01", 100],
        ["2024-01-01", 100],
        ["2024-02-01", 200],
    ]})
    response = upload_and_process(client, "dupes.xlsx", content, XLSX_MIME)
    assert response.json()["worksheets"][0]["duplicate_row_count"] == 1


def test_process_inconsistent_values_flagged(client: TestClient, big_upload_limit) -> None:
    content = build_xlsx({"Sheet1": [
        ["Date", "Revenue"],
        ["2024-01-01", 100],
        ["2024-02-01", 200],
        ["2024-03-01", 300],
        ["2024-04-01", 400],
        ["2024-05-01", 500],
        ["2024-06-01", 600],
        ["2024-07-01", 700],
        ["2024-08-01", 800],
        ["2024-09-01", 900],
        ["2024-10-01", "oops"],
    ]})
    response = upload_and_process(client, "inconsistent.xlsx", content, XLSX_MIME)
    revenue = next(c for c in response.json()["worksheets"][0]["columns"] if c["name"] == "Revenue")
    assert revenue["inferred_type"] == "integer"
    assert revenue["inconsistent_values"]["count"] == 1
    assert "oops" in revenue["inconsistent_values"]["examples"]


def test_process_ambiguous_normalization_not_renamed(client: TestClient, big_upload_limit) -> None:
    # Two source columns both mean "revenue" -> neither is renamed, both surfaced as a warning.
    content = build_xlsx({"Sheet1": [
        ["Date", "Revenue", "Total Revenue"],
        ["2024-01-01", 100, 100],
    ]})
    response = upload_and_process(client, "ambiguous.xlsx", content, XLSX_MIME)
    sheet = response.json()["worksheets"][0]
    assert sheet["ambiguous_mappings"], "expected an ambiguous mapping to be reported"
    assert sheet["ambiguous_mappings"][0]["canonical_concept"] == "revenue"
    assert "Revenue" not in sheet["normalization_mappings"]
    assert "Total Revenue" not in sheet["normalization_mappings"]
    assert any("more than one financial concept" in w for w in sheet["warnings"])


def test_process_corrupt_xlsx_fails_gracefully(client: TestClient, big_upload_limit) -> None:
    # Passes Phase 1's structural check (has the required OOXML parts) but
    # the workbook XML itself is garbage, so openpyxl cannot parse it.
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("[Content_Types].xml", "not real content types xml")
        archive.writestr("xl/workbook.xml", "<<<not xml at all>>>")
    content = buf.getvalue()

    response = upload_and_process(client, "corrupt.xlsx", content, XLSX_MIME)
    assert response.status_code == 201  # a failed processing run is still a valid API result
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["worksheets"] == []
    assert "corrupted" in body["error_message"].lower() or "unsupported" in body["error_message"].lower()
    # No internals leaked to the client.
    assert "openpyxl" not in body["error_message"]
    assert "Traceback" not in body["error_message"]


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def test_process_valid_csv(client: TestClient) -> None:
    content = b"Date,Revenue\n2024-01-01,100\n2024-02-01,200\n"
    response = upload_and_process(client, "data.csv", content, "text/csv")
    assert response.status_code == 201
    sheet = response.json()["worksheets"][0]
    assert sheet["sheet_name"] == "csv"
    assert sheet["row_count"] == 2
    assert sheet["csv_delimiter"] == ","


def test_process_csv_missing_values(client: TestClient) -> None:
    content = b"Date,Revenue\n2024-01-01,100\n2024-02-01,\n"
    response = upload_and_process(client, "missing.csv", content, "text/csv")
    revenue = next(c for c in response.json()["worksheets"][0]["columns"] if c["name"] == "Revenue")
    assert revenue["missing_count"] == 1


def test_process_csv_duplicate_rows(client: TestClient) -> None:
    content = b"Date,Revenue\n2024-01-01,100\n2024-01-01,100\n"
    response = upload_and_process(client, "dupes.csv", content, "text/csv")
    assert response.json()["worksheets"][0]["duplicate_row_count"] == 1


def test_process_csv_datatype_inference(client: TestClient) -> None:
    content = b"Date,Revenue,Active,Label\n2024-01-01,100,true,alpha\n2024-02-01,200,false,beta\n"
    response = upload_and_process(client, "types.csv", content, "text/csv")
    columns = {c["name"]: c["inferred_type"] for c in response.json()["worksheets"][0]["columns"]}
    assert columns == {"Date": "date", "Revenue": "integer", "Active": "boolean", "Label": "string"}


def test_process_csv_alternative_delimiter(client: TestClient) -> None:
    content = b"Date;Revenue\n2024-01-01;100\n2024-02-01;200\n"
    response = upload_and_process(client, "semicolon.csv", content, "text/csv")
    assert response.status_code == 201
    sheet = response.json()["worksheets"][0]
    assert sheet["csv_delimiter"] == ";"
    assert sheet["row_count"] == 2


def test_process_csv_inconsistent_values(client: TestClient) -> None:
    rows = "\n".join(f"2024-{i:02d}-01,{i * 10}" for i in range(1, 10))
    content = ("Date,Revenue\n" + rows + "\n2024-10-01,bad_value\n").encode()
    response = upload_and_process(client, "inconsistent.csv", content, "text/csv")
    revenue = next(c for c in response.json()["worksheets"][0]["columns"] if c["name"] == "Revenue")
    assert revenue["inconsistent_values"]["count"] == 1


def test_process_malformed_csv_does_not_crash(client: TestClient) -> None:
    # Ragged rows with inconsistent column counts.
    content = b"A,B,C\n1,2,3\n4,5\n6,7,8,9\n10,11,12\n"
    response = upload_and_process(client, "ragged.csv", content, "text/csv")
    assert response.status_code == 201
    assert response.json()["status"] == "COMPLETE"


def test_process_effectively_empty_csv(client: TestClient) -> None:
    # Not zero bytes (Phase 1 already rejects that) but structurally blank.
    content = b",,,\n,,,\n"
    response = upload_and_process(client, "blank.csv", content, "text/csv")
    assert response.status_code == 201
    sheet = response.json()["worksheets"][0]
    assert sheet["is_empty"] is True
    assert sheet["cleaned_data_status"] == "SKIPPED"


def test_process_csv_header_handling(client: TestClient) -> None:
    content = b"generated by accounting system\nDate,Revenue\n2024-01-01,100\n2024-02-01,200\n"
    response = upload_and_process(client, "titled.csv", content, "text/csv")
    sheet = response.json()["worksheets"][0]
    assert sheet["header_row_index"] == 1
    assert sheet["row_count"] == 2


# ---------------------------------------------------------------------------
# Security / reliability
# ---------------------------------------------------------------------------


def test_process_original_file_never_modified(client: TestClient, big_upload_limit) -> None:
    content = build_xlsx({"Sheet1": [["Date", "Revenue"], ["2024-01-01", 100]]})
    upload = client.post("/api/files", files={"file": ("keep.xlsx", content, XLSX_MIME)})
    file_id = upload.json()["id"]
    stored_filename = upload.json()["stored_filename"]

    from app.services import file_storage

    before = (file_storage.upload_directory() / stored_filename).read_bytes()
    assert before == content

    response = client.post(f"/api/files/{file_id}/process")
    assert response.status_code == 201

    after = (file_storage.upload_directory() / stored_filename).read_bytes()
    assert after == content, "the original uploaded file must never be modified"


def test_process_unexpected_columns_handled_safely(client: TestClient) -> None:
    content = b"Date,Revenue,Some Random Column\n2024-01-01,100,xyz\n"
    response = upload_and_process(client, "extra.csv", content, "text/csv")
    assert response.status_code == 201
    columns = {c["name"] for c in response.json()["worksheets"][0]["columns"]}
    assert "Some Random Column" in columns
    # An unrecognized column is kept, not dropped or guessed at.
    unmapped = next(c for c in response.json()["worksheets"][0]["columns"] if c["name"] == "Some Random Column")
    assert unmapped["canonical_concept"] is None


def test_process_dataset_too_large_is_reported_not_processed(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MAX_PROCESSING_ROWS", "3")
    get_settings.cache_clear()
    content = b"Date,Revenue\n" + b"".join(f"2024-01-{i:02d},{i}\n".encode() for i in range(1, 10))
    response = upload_and_process(client, "toolarge.csv", content, "text/csv")
    assert response.status_code == 201
    sheet = response.json()["worksheets"][0]
    assert sheet["cleaned_data_status"] == "SKIPPED"
    assert any("DATASET_TOO_LARGE" in e for e in sheet["errors"])


def test_process_file_not_found_returns_404(client: TestClient) -> None:
    response = client.post("/api/files/00000000-0000-0000-0000-000000000000/process")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "FILE_NOT_FOUND"


def test_process_unsupported_file_type_rejected(client: TestClient) -> None:
    pdf_content = b"%PDF-1.4\n%mock\n%%EOF"
    upload = client.post("/api/files", files={"file": ("doc.pdf", pdf_content, "application/pdf")})
    assert upload.status_code == 201
    file_id = upload.json()["id"]

    response = client.post(f"/api/files/{file_id}/process")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_get_processing_result_before_processing_returns_404(client: TestClient) -> None:
    content = b"Date,Revenue\n2024-01-01,100\n"
    upload = client.post("/api/files", files={"file": ("data.csv", content, "text/csv")})
    file_id = upload.json()["id"]

    response = client.get(f"/api/files/{file_id}/process")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROCESSING_RESULT_NOT_FOUND"


def test_get_processing_result_returns_latest(client: TestClient) -> None:
    content = b"Date,Revenue\n2024-01-01,100\n"
    upload = client.post("/api/files", files={"file": ("data.csv", content, "text/csv")})
    file_id = upload.json()["id"]

    posted = client.post(f"/api/files/{file_id}/process")
    fetched = client.get(f"/api/files/{file_id}/process")

    assert fetched.status_code == 200
    assert fetched.json()["id"] == posted.json()["id"]
