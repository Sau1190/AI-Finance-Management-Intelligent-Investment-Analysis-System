"""Phase 3 — Excel export tests.

Covers generating a formatted workbook from Phase 2's already-verified
output, the download/metadata endpoints, and the edge cases: exporting
before processing, exporting a failed processing run, and original-file
integrity. Does not test anything about financial metrics, sentiment, or
scoring — this phase only reassembles what Phase 1/2 already produced.
"""

import io
import zipfile
from datetime import datetime

import openpyxl
import pytest
from fastapi.testclient import TestClient

# Reuse Phase 2's fixtures/helpers rather than duplicating them.
from tests.test_processing import XLSX_MIME, big_upload_limit, build_xlsx  # noqa: F401

VALID_CSV = b"Date,Revenue\n2024-01-01,100\n2024-02-01,200\n"


def upload_process_export(client: TestClient, filename: str, content: bytes, content_type: str) -> dict:
    upload = client.post("/api/files", files={"file": (filename, content, content_type)})
    assert upload.status_code == 201, upload.text
    file_id = upload.json()["id"]
    process = client.post(f"/api/files/{file_id}/process")
    assert process.status_code == 201, process.text
    export = client.post(f"/api/files/{file_id}/export")
    return file_id, export


def test_export_valid_xlsx_single_sheet(client: TestClient, big_upload_limit) -> None:
    content = build_xlsx({"Sheet1": [
        ["Date", "Ticker", "Revenue"],
        ["2024-01-01", "ACME", 5000],
        ["2024-02-01", "ACME", 5200],
    ]})
    file_id, export = upload_process_export(client, "report.xlsx", content, XLSX_MIME)
    assert export.status_code == 201
    body = export.json()
    assert body["status"] == "COMPLETE"
    assert body["sheet_names"] == ["Summary", "Raw Data", "Cleaned Data"]
    assert body["storage_key"].startswith("exports/")

    download = client.get(f"/api/files/{file_id}/export/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    workbook = openpyxl.load_workbook(io.BytesIO(download.content))
    assert workbook.sheetnames == ["Summary", "Raw Data", "Cleaned Data"]

    summary_rows = list(workbook["Summary"].iter_rows(values_only=True))
    assert summary_rows[1][0] == "Sheet1"  # worksheet name column

    raw_rows = list(workbook["Raw Data"].iter_rows(values_only=True))
    assert raw_rows[0] == ("Date", "Ticker", "Revenue")
    assert raw_rows[1][1] == "ACME"

    cleaned_rows = list(workbook["Cleaned Data"].iter_rows(values_only=True))
    assert cleaned_rows[0] == ("date", "ticker", "revenue")


def test_export_multi_sheet_xlsx_uses_per_sheet_titles(client: TestClient, big_upload_limit) -> None:
    content = build_xlsx({
        "Q1": [["Date", "Revenue"], ["2024-01-01", 100]],
        "Q2": [["Date", "Revenue"], ["2024-04-01", 200]],
    })
    file_id, export = upload_process_export(client, "multi.xlsx", content, XLSX_MIME)
    assert export.status_code == 201
    assert export.json()["sheet_names"] == [
        "Summary", "Raw - Q1", "Cleaned - Q1", "Raw - Q2", "Cleaned - Q2"
    ]

    download = client.get(f"/api/files/{file_id}/export/download")
    workbook = openpyxl.load_workbook(io.BytesIO(download.content))
    assert workbook.sheetnames == ["Summary", "Raw - Q1", "Cleaned - Q1", "Raw - Q2", "Cleaned - Q2"]


def test_export_valid_csv(client: TestClient) -> None:
    file_id, export = upload_process_export(client, "data.csv", VALID_CSV, "text/csv")
    assert export.status_code == 201
    download = client.get(f"/api/files/{file_id}/export/download")
    workbook = openpyxl.load_workbook(io.BytesIO(download.content))
    assert workbook.sheetnames == ["Summary", "Raw Data", "Cleaned Data"]


def test_export_keeps_formula_like_uploaded_values_as_text(client: TestClient) -> None:
    content = b'Company,Notes\nACME,"=HYPERLINK(""https://example.invalid"",""open"")"\n'
    file_id, export = upload_process_export(client, "formula.csv", content, "text/csv")
    assert export.status_code == 201

    download = client.get(f"/api/files/{file_id}/export/download")
    workbook = openpyxl.load_workbook(io.BytesIO(download.content), data_only=False)
    raw_cell = workbook["Raw Data"]["B2"]
    cleaned_cell = workbook["Cleaned Data"]["B2"]
    expected = '=HYPERLINK("https://example.invalid","open")'
    assert raw_cell.value == expected and raw_cell.data_type == "s"
    assert cleaned_cell.value == expected and cleaned_cell.data_type == "s"


def test_integer_coercion_is_exact_and_rejects_fractional_values() -> None:
    from app.services.excel_export import _coerce_cell

    assert _coerce_cell("1.5", "integer") is None
    assert _coerce_cell("9007199254740993", "integer") == 9007199254740993


def test_export_skipped_empty_worksheet_reflected_in_summary(client: TestClient, big_upload_limit) -> None:
    content = build_xlsx({"Data": [["Date", "Revenue"], ["2024-01-01", 100]], "Notes": []})
    file_id, export = upload_process_export(client, "withnotes.xlsx", content, XLSX_MIME)
    assert export.status_code == 201

    download = client.get(f"/api/files/{file_id}/export/download")
    workbook = openpyxl.load_workbook(io.BytesIO(download.content))
    # An empty worksheet still gets a Raw sheet (even if blank) but no Cleaned sheet.
    assert "Raw - Notes" in workbook.sheetnames
    assert "Cleaned - Notes" not in workbook.sheetnames

    summary = {row[0]: row for row in workbook["Summary"].iter_rows(values_only=True)}
    assert summary["Notes"][6] == "SKIPPED"  # Cleaned Data column


def test_export_of_failed_processing_is_summary_only(client: TestClient, big_upload_limit) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "not real content types xml")
        archive.writestr("xl/workbook.xml", "<<<not xml at all>>>")
    corrupt = buffer.getvalue()

    file_id, export = upload_process_export(client, "corrupt.xlsx", corrupt, XLSX_MIME)
    assert export.status_code == 201
    body = export.json()
    assert body["status"] == "COMPLETE"  # the export itself succeeded
    assert body["sheet_names"] == ["Summary"]

    download = client.get(f"/api/files/{file_id}/export/download")
    workbook = openpyxl.load_workbook(io.BytesIO(download.content))
    assert workbook.sheetnames == ["Summary"]
    first_cell = workbook["Summary"]["A1"].value
    assert "did not complete" in first_cell.lower()


def test_export_before_processing_returns_404(client: TestClient) -> None:
    upload = client.post("/api/files", files={"file": ("data.csv", VALID_CSV, "text/csv")})
    file_id = upload.json()["id"]

    response = client.post(f"/api/files/{file_id}/export")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROCESSING_RESULT_NOT_FOUND"


def test_export_cleaned_sheet_uses_real_typed_cells_for_normalized_columns(
    client: TestClient, big_upload_limit
) -> None:
    # Regression test: Phase 2 renames a normalized column's header to its
    # canonical concept in the cleaned CSV (e.g. "Revenue" -> "revenue").
    # column_types must be keyed by that renamed header, or number/date
    # coercion silently never applies to exactly the columns that matter
    # most — this previously left every normalized column as plain text.
    content = build_xlsx({"Sheet1": [
        ["Date", "Revenue", "Net Income"],
        ["2024-01-01", 5000, 800],
        ["2024-02-01", 5200, 850],
    ]})
    file_id, export = upload_process_export(client, "typed.xlsx", content, XLSX_MIME)
    assert export.status_code == 201

    download = client.get(f"/api/files/{file_id}/export/download")
    workbook = openpyxl.load_workbook(io.BytesIO(download.content))
    ws = workbook["Cleaned Data"]
    header = [cell.value for cell in ws[1]]
    assert header == ["date", "revenue", "net_income"]

    row2 = list(ws.iter_rows(min_row=2, max_row=2))[0]
    date_cell, revenue_cell, income_cell = row2
    assert isinstance(date_cell.value, datetime)
    assert date_cell.number_format == "yyyy-mm-dd"
    assert revenue_cell.value == 5000
    assert isinstance(revenue_cell.value, int)
    assert revenue_cell.number_format == "#,##0"
    assert income_cell.value == 800
    assert isinstance(income_cell.value, int)


def test_export_file_not_found_returns_404(client: TestClient) -> None:
    response = client.post("/api/files/00000000-0000-0000-0000-000000000000/export")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "FILE_NOT_FOUND"


def test_get_export_result_before_export_returns_404(client: TestClient) -> None:
    upload = client.post("/api/files", files={"file": ("data.csv", VALID_CSV, "text/csv")})
    file_id = upload.json()["id"]
    client.post(f"/api/files/{file_id}/process")

    response = client.get(f"/api/files/{file_id}/export")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "EXPORT_NOT_FOUND"


def test_get_export_result_returns_latest(client: TestClient) -> None:
    file_id, posted = upload_process_export(client, "data.csv", VALID_CSV, "text/csv")
    fetched = client.get(f"/api/files/{file_id}/export")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == posted.json()["id"]


def test_download_without_export_returns_404(client: TestClient) -> None:
    upload = client.post("/api/files", files={"file": ("data.csv", VALID_CSV, "text/csv")})
    file_id = upload.json()["id"]
    client.post(f"/api/files/{file_id}/process")

    response = client.get(f"/api/files/{file_id}/export/download")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "EXPORT_NOT_FOUND"


def test_download_file_not_found_returns_404(client: TestClient) -> None:
    response = client.get("/api/files/00000000-0000-0000-0000-000000000000/export/download")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "FILE_NOT_FOUND"


def test_export_never_modifies_original_file(client: TestClient, big_upload_limit) -> None:
    content = build_xlsx({"Sheet1": [["Date", "Revenue"], ["2024-01-01", 100]]})
    upload = client.post("/api/files", files={"file": ("keep.xlsx", content, XLSX_MIME)})
    file_id = upload.json()["id"]
    stored_filename = upload.json()["stored_filename"]

    client.post(f"/api/files/{file_id}/process")
    client.post(f"/api/files/{file_id}/export")

    from app.services import file_storage

    assert (file_storage.upload_directory() / stored_filename).read_bytes() == content


def test_export_response_never_leaks_internals_on_failure(client: TestClient, big_upload_limit) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "x")
        archive.writestr("xl/workbook.xml", "not xml")
    corrupt = buffer.getvalue()
    file_id, export = upload_process_export(client, "corrupt.xlsx", corrupt, XLSX_MIME)
    assert export.status_code == 201
    assert "Traceback" not in str(export.json())
    assert "openpyxl" not in str(export.json())
