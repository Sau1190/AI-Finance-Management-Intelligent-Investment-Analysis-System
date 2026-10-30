"""Phase 1 — file management tests.

Covers: valid uploads per type, invalid extension/content/size/filename,
MIME mismatch, duplicate filenames, storage uniqueness, API errors, and
service-level failure paths (database/storage). No financial analysis
is exercised here — Phase 1 only validates, stores, and records metadata.
"""

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.exceptions import FileIntakeError
from app.services import file_service, file_storage


# ---------------------------------------------------------------------------
# Fixtures — real content for each supported type, plus deliberately broken
# variants used to prove the validators reject what they should.
# ---------------------------------------------------------------------------

def make_valid_xlsx_bytes() -> bytes:
    """A minimal but structurally real OOXML package: valid ZIP containing
    the parts an XLSX workbook must have. This does not have to be openable
    by Excel — Phase 1 only verifies file *intake*, not workbook contents.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?><Types/>',
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?><workbook/>',
        )
        archive.writestr("_rels/.rels", "<Relationships/>")
    return buffer.getvalue()


def make_fake_xlsx_bytes() -> bytes:
    """A real ZIP file (so a bare `PK` check would wrongly accept it) that is
    NOT an OOXML workbook — no `[Content_Types].xml`, no `xl/workbook.xml`.
    This is the regression test for the original validation flaw.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "just a plain zip, not a workbook")
    return buffer.getvalue()


VALID_CSV = b"name,amount\nRent,1000\nGroceries,250\n"
VALID_PDF = b"%PDF-1.4\n%mock pdf content for tests\n%%EOF"


# ---------------------------------------------------------------------------
# Valid uploads
# ---------------------------------------------------------------------------

def test_upload_valid_pdf_succeeds(client: TestClient) -> None:
    response = client.post(
        "/api/files",
        files={"file": ("statement.pdf", VALID_PDF, "application/pdf")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["file_type"] == "pdf"
    assert body["original_filename"] == "statement.pdf"
    assert body["processing_status"] == "READY"
    assert body["size_bytes"] == len(VALID_PDF)
    assert "storage_key" in body and body["storage_key"].startswith("uploads/")


def test_upload_valid_csv_succeeds(client: TestClient) -> None:
    response = client.post(
        "/api/files",
        files={"file": ("budget.csv", VALID_CSV, "text/csv")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["file_type"] == "csv"
    assert body["processing_status"] == "READY"


def test_upload_valid_xlsx_succeeds(client: TestClient) -> None:
    content = make_valid_xlsx_bytes()
    response = client.post(
        "/api/files",
        files={
            "file": (
                "portfolio.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["file_type"] == "xlsx"
    assert body["processing_status"] == "READY"


# ---------------------------------------------------------------------------
# The core regression: a plain ZIP renamed to .xlsx must now be rejected
# ---------------------------------------------------------------------------

def test_upload_rejects_zip_masquerading_as_xlsx(client: TestClient) -> None:
    content = make_fake_xlsx_bytes()
    response = client.post(
        "/api/files",
        files={"file": ("fake.xlsx", content, "application/zip")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSUPPORTED_FILE_TYPE"


# ---------------------------------------------------------------------------
# Extension / size / emptiness
# ---------------------------------------------------------------------------

def test_upload_rejects_unsupported_extension(client: TestClient) -> None:
    response = client.post(
        "/api/files",
        files={"file": ("virus.exe", b"MZ-not-a-real-binary", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_upload_rejects_empty_file(client: TestClient) -> None:
    response = client.post(
        "/api/files",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EMPTY_FILE"


def test_upload_rejects_oversized_file(client: TestClient) -> None:
    # conftest sets MAX_UPLOAD_BYTES=1024 for the test environment.
    oversized = b"a,b\n" + (b"1,2\n" * 500)
    assert len(oversized) > 1024
    response = client.post(
        "/api/files",
        files={"file": ("big.csv", oversized, "text/csv")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "FILE_TOO_LARGE"


# ---------------------------------------------------------------------------
# Content / extension mismatch (declared type must match actual bytes)
# ---------------------------------------------------------------------------

def test_upload_rejects_pdf_content_named_as_csv(client: TestClient) -> None:
    response = client.post(
        "/api/files",
        files={"file": ("data.csv", VALID_PDF, "text/csv")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_upload_rejects_csv_content_named_as_pdf(client: TestClient) -> None:
    response = client.post(
        "/api/files",
        files={"file": ("report.pdf", VALID_CSV, "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_upload_rejects_mismatched_mime_header(client: TestClient) -> None:
    # Content and extension are both genuinely CSV, but the declared
    # Content-Type is not one this project allows for CSV.
    response = client.post(
        "/api/files",
        files={"file": ("budget.csv", VALID_CSV, "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSUPPORTED_FILE_TYPE"


# ---------------------------------------------------------------------------
# Filename safety
# ---------------------------------------------------------------------------

def test_upload_sanitizes_path_traversal_filename(client: TestClient) -> None:
    response = client.post(
        "/api/files",
        files={"file": ("../../etc/passwd.csv", VALID_CSV, "text/csv")},
    )
    assert response.status_code == 201
    body = response.json()
    # Only the final path component survives; no traversal segments remain.
    assert body["original_filename"] == "passwd.csv"
    assert ".." not in body["storage_key"]
    assert "/" not in body["stored_filename"] and "\\" not in body["stored_filename"]


def test_upload_sanitizes_windows_style_traversal_filename(client: TestClient) -> None:
    response = client.post(
        "/api/files",
        files={"file": ("..\\..\\windows\\system32\\config.csv", VALID_CSV, "text/csv")},
    )
    assert response.status_code == 201
    assert response.json()["original_filename"] == "config.csv"


def test_upload_rejects_dot_dot_filename(client: TestClient) -> None:
    response = client.post(
        "/api/files",
        files={"file": ("..", VALID_CSV, "text/csv")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_FILENAME"


def test_upload_rejects_blank_filename(client: TestClient) -> None:
    # A filename-less multipart part never reaches our own validators —
    # FastAPI's own request parsing rejects it first. We still assert our
    # normalized error envelope and confirm no internal details leak.
    response = client.post(
        "/api/files",
        files={"file": ("", VALID_CSV, "text/csv")},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "INVALID_REQUEST"
    assert "UploadFile" not in detail["message"]


# ---------------------------------------------------------------------------
# Duplicate / conflicting original filenames
# ---------------------------------------------------------------------------

def test_upload_allows_duplicate_original_filenames(client: TestClient) -> None:
    first = client.post(
        "/api/files",
        files={"file": ("budget.csv", VALID_CSV, "text/csv")},
    )
    second = client.post(
        "/api/files",
        files={"file": ("budget.csv", VALID_CSV, "text/csv")},
    )
    assert first.status_code == 201 and second.status_code == 201
    first_body, second_body = first.json(), second.json()

    assert first_body["original_filename"] == second_body["original_filename"] == "budget.csv"
    # Same declared name, but distinct identities on disk and in the DB.
    assert first_body["id"] != second_body["id"]
    assert first_body["stored_filename"] != second_body["stored_filename"]
    assert first_body["storage_key"] != second_body["storage_key"]


# ---------------------------------------------------------------------------
# List / get / missing-id API behavior
# ---------------------------------------------------------------------------

def test_list_uploaded_files_returns_recent_items(client: TestClient) -> None:
    client.post("/api/files", files={"file": ("a.csv", VALID_CSV, "text/csv")})
    client.post("/api/files", files={"file": ("b.csv", VALID_CSV, "text/csv")})

    response = client.get("/api/files")
    assert response.status_code == 200
    items = response.json()["items"]
    names = {item["original_filename"] for item in items}
    assert {"a.csv", "b.csv"}.issubset(names)


def test_get_uploaded_file_by_id_returns_metadata(client: TestClient) -> None:
    uploaded = client.post(
        "/api/files",
        files={"file": ("statement.pdf", VALID_PDF, "application/pdf")},
    ).json()

    response = client.get(f"/api/files/{uploaded['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == uploaded["id"]


def test_get_uploaded_file_missing_id_returns_404(client: TestClient) -> None:
    response = client.get("/api/files/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "FILE_NOT_FOUND"


# ---------------------------------------------------------------------------
# Storage layer — uniqueness and overwrite protection
# ---------------------------------------------------------------------------

def test_storage_never_reuses_or_overwrites_filenames(tmp_path) -> None:
    first_name, first_key = file_storage.save_original_bytes(VALID_CSV, "csv")
    second_name, second_key = file_storage.save_original_bytes(VALID_CSV, "csv")

    assert first_name != second_name
    assert first_key != second_key

    directory = file_storage.upload_directory()
    assert (directory / first_name).read_bytes() == VALID_CSV
    assert (directory / second_name).read_bytes() == VALID_CSV


def test_storage_raises_after_exhausting_unique_name_attempts(monkeypatch) -> None:
    # Force every generated name to collide so the retry loop is exhausted
    # and the documented STORAGE_FAILURE path is exercised.
    directory = file_storage.upload_directory()
    collision_path = directory / "always-taken.csv"
    collision_path.write_bytes(b"pre-existing")

    monkeypatch.setattr(file_storage, "unique_stored_filename", lambda file_type: "always-taken.csv")

    with pytest.raises(FileIntakeError) as excinfo:
        file_storage.save_original_bytes(VALID_CSV, "csv")
    assert excinfo.value.code == "STORAGE_FAILURE"
    # The pre-existing file must not have been touched.
    assert collision_path.read_bytes() == b"pre-existing"


# ---------------------------------------------------------------------------
# Service layer — database failure path (no orphaned file should be stored)
# ---------------------------------------------------------------------------

def test_ingest_upload_fails_cleanly_when_database_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        file_service,
        "check_database_connection",
        lambda: {"connected": False, "error": "OperationalError"},
    )

    directory = file_storage.upload_directory()
    before = set(directory.iterdir())

    assert SessionLocal is not None
    db = SessionLocal()
    try:
        with pytest.raises(FileIntakeError) as excinfo:
            file_service.ingest_upload(
                db,
                filename="budget.csv",
                content_type="text/csv",
                content=VALID_CSV,
            )
        assert excinfo.value.code == "DATABASE_FAILURE"
        assert excinfo.value.status_code == 503
    finally:
        db.close()

    # Validation/storage never ran because the database check happens first.
    after = set(directory.iterdir())
    assert before == after
