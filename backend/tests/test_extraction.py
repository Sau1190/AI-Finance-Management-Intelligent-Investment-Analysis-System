"""Phase 4 — PDF extraction tests.

Covers literal text/table extraction (no OCR, no interpretation), the
security/reliability guarantees shared with earlier phases (original file
integrity, consistent error envelope, no crash on malformed input), and the
PDF-specific failure modes: encrypted and corrupt files, pages with no
extractable text, and the page-count limit. Does not test anything about
financial interpretation of extracted content — Phase 4 only produces a
literal, inspectable extraction.
"""

import io
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core import database
from app.core.config import get_settings
from app.core.exceptions import ExtractionRequestError
from app.services import file_service, pdf_extraction, pdf_extraction_service

# Reuse Phase 2's fixture rather than duplicating it.
from tests.test_processing import big_upload_limit  # noqa: F401

PDF_MIME = "application/pdf"


def build_pdf(pages: list[dict]) -> bytes:
    """Build a real PDF from a list of page specs:
    {"text": [(x, y, line), ...], "table": [[cell, ...], ...] or None}
    A page with no "text" and no "table" produces a genuinely blank page
    (no text layer at all, like a scanned image).
    """
    doc = pymupdf.open()
    for spec in pages:
        page = doc.new_page()
        for x, y, line in spec.get("text", []):
            page.insert_text((x, y), line)
        table = spec.get("table")
        if table:
            rows, cols = len(table), len(table[0])
            x0, y0, cell_w, cell_h = 50, 300, 60, 30
            xs = [x0 + i * cell_w for i in range(cols + 1)]
            ys = [y0 + i * cell_h for i in range(rows + 1)]
            shape = page.new_shape()
            for x in xs:
                shape.draw_line((x, ys[0]), (x, ys[-1]))
            for y in ys:
                shape.draw_line((xs[0], y), (xs[-1], y))
            shape.finish()
            shape.commit()
            for r, row in enumerate(table):
                for c, value in enumerate(row):
                    page.insert_text((xs[c] + 5, ys[r] + 20), str(value))
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def build_encrypted_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page()
    buf = io.BytesIO()
    doc.save(buf, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
    doc.close()
    return buf.getvalue()


def upload_and_extract(client: TestClient, filename: str, content: bytes) -> dict:
    upload = client.post("/api/files", files={"file": (filename, content, PDF_MIME)})
    assert upload.status_code == 201, upload.text
    file_id = upload.json()["id"]
    response = client.post(f"/api/files/{file_id}/extract")
    return file_id, response


# ---------------------------------------------------------------------------
# Valid extraction
# ---------------------------------------------------------------------------


def test_extract_single_page_text(client: TestClient) -> None:
    content = build_pdf([{"text": [(50, 50, "Quarterly Report"), (50, 80, "Prepared for investors")]}])
    file_id, response = upload_and_extract(client, "simple.pdf", content)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "COMPLETE"
    assert body["page_count"] == 1
    page = body["pages"][0]
    assert page["page_number"] == 1
    assert "Quarterly Report" in page["text_preview"]
    assert page["char_count"] > 0
    assert page["text_storage_key"].startswith("extracts/")
    assert page["warnings"] == []


def test_extract_multi_page_pdf(client: TestClient, big_upload_limit) -> None:
    content = build_pdf([
        {"text": [(50, 50, "Page one")]},
        {"text": [(50, 50, "Page two")]},
        {"text": [(50, 50, "Page three")]},
    ])
    file_id, response = upload_and_extract(client, "multi.pdf", content)
    assert response.status_code == 201
    body = response.json()
    assert body["page_count"] == 3
    numbers = [p["page_number"] for p in body["pages"]]
    assert numbers == [1, 2, 3]
    previews = [p["text_preview"] for p in body["pages"]]
    assert "Page one" in previews[0]
    assert "Page two" in previews[1]
    assert "Page three" in previews[2]


def test_extract_detects_table(client: TestClient, big_upload_limit) -> None:
    content = build_pdf([{
        "text": [(50, 50, "Revenue Statement")],
        "table": [["Date", "Revenue"], ["2024-01-01", "5000"]],
    }])
    file_id, response = upload_and_extract(client, "withtable.pdf", content)
    assert response.status_code == 201
    page = response.json()["pages"][0]
    assert page["table_count"] == 1
    table = page["tables"][0]
    assert table["row_count"] == 2
    assert table["column_count"] == 2
    assert table["preview_rows"][0] == ["Date", "Revenue"]
    assert table["storage_key"].startswith("extracts/")


def test_extract_page_with_no_text_reports_warning_not_error(client: TestClient) -> None:
    content = build_pdf([{"text": [(50, 50, "Has text")]}, {}])  # second page genuinely blank
    file_id, response = upload_and_extract(client, "blankpage.pdf", content)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "COMPLETE"
    blank_page = body["pages"][1]
    assert blank_page["char_count"] == 0
    assert blank_page["text_storage_key"] is None
    assert any("No extractable text" in w for w in blank_page["warnings"])
    assert "OCR" in blank_page["warnings"][0]  # states plainly that OCR was not attempted


def test_extract_table_preview_bounded(client: TestClient, big_upload_limit) -> None:
    rows = [["Date", "Revenue"]] + [[f"2024-{i:02d}-01", str(i * 100)] for i in range(1, 10)]
    content = build_pdf([{"table": rows}])
    file_id, response = upload_and_extract(client, "longtable.pdf", content)
    table = response.json()["pages"][0]["tables"][0]
    assert table["row_count"] == 10
    assert len(table["preview_rows"]) == 5  # bounded preview, full table still in storage_key


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


def test_extract_encrypted_pdf_fails_gracefully(client: TestClient, big_upload_limit) -> None:
    content = build_encrypted_pdf()
    file_id, response = upload_and_extract(client, "locked.pdf", content)
    assert response.status_code == 201  # a failed extraction run is still a valid API result
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["pages"] == []
    assert "password-protected" in body["error_message"].lower()
    # Never attempts to guess a password or leak internals.
    assert "secret" not in body["error_message"]


def test_extract_corrupt_pdf_fails_gracefully(client: TestClient) -> None:
    # Passes Phase 1's %PDF sniff but has no real PDF structure after it.
    content = b"%PDF-1.4\n%not a real pdf structure" + b"\x00" * 40
    file_id, response = upload_and_extract(client, "corrupt.pdf", content)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["pages"] == []
    assert "corrupted" in body["error_message"].lower() or "unsupported" in body["error_message"].lower()
    assert "Traceback" not in body["error_message"]
    assert "pymupdf" not in body["error_message"].lower()


def test_extract_too_many_pages_reported_not_processed(client: TestClient, monkeypatch, big_upload_limit) -> None:
    monkeypatch.setenv("MAX_PDF_PAGES", "2")
    get_settings.cache_clear()
    content = build_pdf([{"text": [(50, 50, f"Page {i}")]} for i in range(5)])
    file_id, response = upload_and_extract(client, "toolarge.pdf", content)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["page_count"] == 5
    assert body["pages"] == []
    assert "PDF_TOO_LARGE" in body["error_message"]


def test_extract_unsupported_file_type_rejected(client: TestClient) -> None:
    upload = client.post("/api/files", files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")})
    assert upload.status_code == 201
    file_id = upload.json()["id"]

    response = client.post(f"/api/files/{file_id}/extract")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSUPPORTED_FILE_TYPE"


# ---------------------------------------------------------------------------
# Security / reliability
# ---------------------------------------------------------------------------


def test_extract_original_file_never_modified(client: TestClient) -> None:
    content = build_pdf([{"text": [(50, 50, "Keep me intact")]}])
    upload = client.post("/api/files", files={"file": ("keep.pdf", content, PDF_MIME)})
    file_id = upload.json()["id"]
    stored_filename = upload.json()["stored_filename"]

    from app.services import file_storage

    before = (file_storage.upload_directory() / stored_filename).read_bytes()
    assert before == content

    response = client.post(f"/api/files/{file_id}/extract")
    assert response.status_code == 201

    after = (file_storage.upload_directory() / stored_filename).read_bytes()
    assert after == content, "the original uploaded PDF must never be modified"


def test_extract_file_not_found_returns_404(client: TestClient) -> None:
    response = client.post("/api/files/00000000-0000-0000-0000-000000000000/extract")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "FILE_NOT_FOUND"


def test_get_extraction_result_before_extraction_returns_404(client: TestClient) -> None:
    content = build_pdf([{"text": [(50, 50, "Hello")]}])
    upload = client.post("/api/files", files={"file": ("fresh.pdf", content, PDF_MIME)})
    file_id = upload.json()["id"]

    response = client.get(f"/api/files/{file_id}/extract")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "EXTRACTION_RESULT_NOT_FOUND"


def test_get_extraction_result_returns_latest(client: TestClient) -> None:
    content = build_pdf([{"text": [(50, 50, "Hello")]}])
    file_id, posted = upload_and_extract(client, "data.pdf", content)
    fetched = client.get(f"/api/files/{file_id}/extract")

    assert fetched.status_code == 200
    assert fetched.json()["id"] == posted.json()["id"]


# ---------------------------------------------------------------------------
# Storage failures — a result is never COMPLETE if required artifacts are missing
#
# Chosen outcome: all-or-nothing. If any page's text or any table cannot be
# saved, the run is FAILED (HTTP 201, inspectable), reports no pages, and every
# artifact already written during that run is deleted.
# ---------------------------------------------------------------------------


def extracts_files() -> list[str]:
    return sorted(path.name for path in pdf_extraction.extracts_directory().iterdir())


def _storage_error(message: str = "The extracted text could not be saved.") -> ExtractionRequestError:
    return ExtractionRequestError("EXTRACTION_STORAGE_FAILURE", message, status_code=500)


def test_successful_extraction_artifacts_all_exist_on_disk(client: TestClient, big_upload_limit) -> None:
    content = build_pdf([
        {"text": [(50, 50, "Revenue Statement")], "table": [["Date", "Revenue"], ["2024-01-01", "5000"]]},
        {"text": [(50, 50, "Second page")]},
    ])
    file_id, response = upload_and_extract(client, "ok.pdf", content)
    body = response.json()
    assert body["status"] == "COMPLETE"

    keys = []
    for page in body["pages"]:
        if page["text_storage_key"]:
            keys.append(page["text_storage_key"])
        keys.extend(table["storage_key"] for table in page["tables"])
    assert len(keys) == 3  # two page texts + one table
    for key in keys:
        assert (pdf_extraction.extracts_directory() / Path(key).name).is_file()
    assert len(extracts_files()) == len(keys)  # nothing extra left behind


def test_text_save_failure_marks_run_failed_not_complete(client: TestClient, monkeypatch) -> None:
    content = build_pdf([{"text": [(50, 50, "Some text")]}])
    upload = client.post("/api/files", files={"file": ("a.pdf", content, PDF_MIME)})
    file_id = upload.json()["id"]

    def failing_save(_text):
        raise _storage_error()

    monkeypatch.setattr(pdf_extraction, "save_text", failing_save)
    response = client.post(f"/api/files/{file_id}/extract")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["page_count"] == 1
    assert body["pages"] == []  # no page may describe an artifact that was not saved
    assert "EXTRACTION_STORAGE_FAILURE" in body["error_message"]
    assert "page 1" in body["error_message"]
    assert extracts_files() == []

    # The persisted latest result agrees with the POST response.
    fetched = client.get(f"/api/files/{file_id}/extract").json()
    assert fetched["status"] == "FAILED"
    assert fetched["pages"] == []


def test_text_save_failure_on_later_page_removes_earlier_artifacts(
    client: TestClient, monkeypatch, big_upload_limit
) -> None:
    content = build_pdf([{"text": [(50, 50, f"Page {i}")]} for i in range(3)])
    upload = client.post("/api/files", files={"file": ("b.pdf", content, PDF_MIME)})
    file_id = upload.json()["id"]

    real_save_text = pdf_extraction.save_text
    saved_keys: list[str] = []

    def flaky_save_text(text):
        if len(saved_keys) == 1:  # page 1 saved fine; page 2 fails
            raise _storage_error()
        stored_filename, key = real_save_text(text)
        saved_keys.append(key)
        return stored_filename, key

    monkeypatch.setattr(pdf_extraction, "save_text", flaky_save_text)
    response = client.post(f"/api/files/{file_id}/extract")

    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "FAILED"
    assert body["page_count"] == 3
    assert body["pages"] == []
    assert "page 2" in body["error_message"]
    assert len(saved_keys) == 1, "page 1's artifact was really written before the failure"
    assert extracts_files() == [], "...and was rolled back, not left orphaned"


def test_table_save_failure_removes_same_page_text_artifact(
    client: TestClient, monkeypatch, big_upload_limit
) -> None:
    content = build_pdf([{
        "text": [(50, 50, "Revenue Statement")],
        "table": [["Date", "Revenue"], ["2024-01-01", "5000"]],
    }])
    upload = client.post("/api/files", files={"file": ("c.pdf", content, PDF_MIME)})
    file_id = upload.json()["id"]

    def failing_save_table(_rows):
        raise _storage_error("An extracted table could not be saved.")

    monkeypatch.setattr(pdf_extraction, "save_table_csv", failing_save_table)
    response = client.post(f"/api/files/{file_id}/extract")

    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "FAILED"
    assert body["pages"] == []
    assert "EXTRACTION_STORAGE_FAILURE" in body["error_message"]
    assert extracts_files() == [], "the text file saved before the table failure must be rolled back"


def test_partial_write_is_removed_and_run_fails(client: TestClient, monkeypatch) -> None:
    content = build_pdf([{"text": [(50, 50, "Some text to write")]}])
    upload = client.post("/api/files", files={"file": ("d.pdf", content, PDF_MIME)})
    file_id = upload.json()["id"]

    real_open = Path.open

    class HalfWriteHandle:
        """Creates the real file, writes a few bytes, then fails like a full disk."""

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

    monkeypatch.setattr(Path, "open", open_with_failing_writes)
    response = client.post(f"/api/files/{file_id}/extract")
    monkeypatch.undo()

    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "FAILED"
    assert body["pages"] == []
    assert "No space left" not in body["error_message"]  # no internals leaked
    assert extracts_files() == [], "the truncated half-written file must not be left behind"


def test_unexpected_page_failure_rolls_back_and_fails_without_leaking(
    client: TestClient, monkeypatch, big_upload_limit
) -> None:
    content = build_pdf([{"text": [(50, 50, f"Page {i}")]} for i in range(3)])
    upload = client.post("/api/files", files={"file": ("e.pdf", content, PDF_MIME)})
    file_id = upload.json()["id"]

    real_extract_page = pdf_extraction.extract_page
    calls = {"n": 0}

    def exploding_extract_page(page):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom internal detail")
        return real_extract_page(page)

    monkeypatch.setattr(pdf_extraction, "extract_page", exploding_extract_page)
    response = client.post(f"/api/files/{file_id}/extract")

    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "FAILED"
    assert body["pages"] == []
    assert "page 2" in body["error_message"]
    assert "boom" not in body["error_message"]
    assert extracts_files() == []


def test_delete_artifacts_never_raises_and_reports_what_it_could_not_remove(monkeypatch) -> None:
    _, key = pdf_extraction.save_text("rollback me")
    assert extracts_files() != []

    with monkeypatch.context() as patch:
        def failing_unlink(self, *args, **kwargs):
            raise OSError("permission denied")

        patch.setattr(Path, "unlink", failing_unlink)
        assert pdf_extraction.delete_artifacts([key]) == [key]  # reported, not raised

    assert pdf_extraction.delete_artifacts([key]) == []  # now it can be removed
    assert extracts_files() == []


def test_delete_artifacts_cannot_escape_the_extracts_directory(tmp_path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("must survive")
    pdf_extraction.delete_artifacts([f"../{outside.name}", str(outside)])
    assert outside.read_text() == "must survive"


def test_database_failure_after_artifacts_written_removes_them(client: TestClient, monkeypatch) -> None:
    content = build_pdf([{"text": [(50, 50, "Some text")]}])
    upload = client.post("/api/files", files={"file": ("f.pdf", content, PDF_MIME)})
    file_id = upload.json()["id"]

    db = database.SessionLocal()
    try:
        record = file_service.get_file(db, file_id)

        def failing_commit():
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(db, "commit", failing_commit)
        with pytest.raises(RuntimeError):
            pdf_extraction_service.extract_pdf(db, record)
    finally:
        db.close()

    assert extracts_files() == [], "no orphaned artifacts when the result row could not be saved"
    check_db = database.SessionLocal()
    try:
        assert pdf_extraction_service.get_latest_result(check_db, file_id) is None
    finally:
        check_db.close()
