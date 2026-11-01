"""Phase 14 regression tests: security and failure-handling hardening.

These tests exercise the real service/helper code with a tiny fake database
session and plain ASGI apps, so they need no running server. Each test
guards one confirmed gap from the Phase 14 audit (docs/SECURITY_TESTING.md).
"""

import ast
import asyncio
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook

from app.core import error_envelope
from app.core.config import Settings, get_settings
from app.core.exceptions import FileIntakeError, ProcessingRequestError
from app.core.http_safety import RequestSizeLimitMiddleware, SecurityHeadersMiddleware
from app.models.uploaded_file import UploadedFile
from app.services import data_quality, db_safety, excel_export, export_service, file_processing, processing_service
from app.services.download_names import build_export_filename, safe_download_filename
from app.services.upload_reader import read_upload_limited

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- helpers
class FakeDB:
    """Just enough of a SQLAlchemy session; optionally fails on commit."""

    def __init__(self, fail_commit: bool = False) -> None:
        self.added: list = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_commit = fail_commit

    def add(self, record) -> None:
        self.added.append(record)

    def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("db down; password=SECRET123")
        self.commits += 1

    def refresh(self, record) -> None:
        if not getattr(record, "id", None):
            record.id = f"rid-{len(self.added)}"

    def rollback(self) -> None:
        self.rollbacks += 1


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    uploads, exports = tmp_path / "uploads", tmp_path / "exports"
    uploads.mkdir(exist_ok=True)
    exports.mkdir(exist_ok=True)
    monkeypatch.setenv("UPLOAD_DIR", str(uploads))
    monkeypatch.setenv("EXPORTS_DIR", str(exports))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def exports_listing(base: Path) -> list[str]:
    return sorted(p.name for p in (base / "exports").iterdir())


def make_upload(base: Path, content: bytes, name: str = "t.csv", file_type: str = "csv", stored: str | None = None):
    stored = stored or f"stored-{len(list((base / 'uploads').iterdir()))}.{file_type}"
    (base / "uploads" / stored).write_bytes(content)
    return UploadedFile(id="file-1", original_filename=name, stored_filename=stored, file_type=file_type)


CONTROL_CHAR_CSV = b"Date,Ticker,Revenue\n2024-01-01,ACME,5000\n2024-02-01,AC\x0bME,5200\n"


def two_sheet_xlsx() -> bytes:
    wb = Workbook()
    first = wb.active
    first.title = "One"
    first.append(["Date", "Revenue", "Ticker"])
    first.append(["2024-01-01", 5, "A"])
    second = wb.create_sheet("Two")
    second.append(["Date", "Revenue", "Ticker"])
    second.append(["2024-01-01", 6, "B"])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def worksheet_export(values, sheet_name="S") -> excel_export.WorksheetExport:
    raw = pd.DataFrame([["h"], *[[v] for v in values]])
    cleaned = pd.DataFrame({"h": list(values)})
    return excel_export.WorksheetExport(
        sheet_name=sheet_name, row_count=len(values), column_count=1, missing_total=0,
        duplicate_row_count=0, inconsistent_total=0, cleaned_data_status="GENERATED",
        raw_df=raw, header_row_index=0, cleaned_df=cleaned,
    )


def load(data: bytes):
    return load_workbook(io.BytesIO(data))


# ------------------------------------------------------------- spreadsheet / export content
def test_control_characters_no_longer_crash_the_workbook_build():
    data = excel_export.build_workbook([worksheet_export(["ok", "bad\x0bchar", "x\x01y"])])
    values = [c.value for row in load(data)["Raw Data"].iter_rows() for c in row]
    assert "bad�char" in values and "x�y" in values
    assert not any(isinstance(v, str) and ("\x0b" in v or "\x01" in v) for v in values)


def test_cells_over_the_excel_limit_are_cut_and_reported():
    data = excel_export.build_workbook([worksheet_export(["x" * 40_000])])
    wb = load(data)
    assert max(len(str(c.value)) for c in wb["Raw Data"]["A"]) == excel_export.MAX_CELL_CHARS
    assert excel_export.clean_cell_text("y" * 40_000) == "y" * excel_export.MAX_CELL_CHARS
    summary_values = [c.value for row in wb["Summary"].iter_rows() for c in row]
    assert any(isinstance(v, int) and v >= 1 for v in summary_values[-3:]) or any(
        isinstance(v, str) and "cell(s)" in v for v in summary_values
    )


def test_a_clean_worksheet_gets_no_cleaning_warning():
    sheet = worksheet_export(["a", "b"])
    assert excel_export._with_cleaning_warning(sheet).warnings == []
    assert excel_export._with_cleaning_warning(worksheet_export(["a\x0bb"])).warnings != []


def test_formula_like_cells_stay_literal_text_never_formulas():
    hostile = ["=1+1", "+SUM(A1)", "@SUM(1)", "-2+3", '=HYPERLINK("http://evil.example","x")', "\t=1", "=cmd|' /C calc'!A0"]
    data = excel_export.build_workbook([worksheet_export(hostile)])
    xml = "".join(
        zipfile.ZipFile(io.BytesIO(data)).read(n).decode("utf8", "ignore")
        for n in zipfile.ZipFile(io.BytesIO(data)).namelist()
        if n.startswith("xl/worksheets/")
    )
    assert "<f>" not in xml and "<f " not in xml
    for sheet in ("Raw Data", "Cleaned Data"):
        for cell in load(data)[sheet]["A"][1:]:
            assert cell.data_type != "f"


def test_sheet_titles_are_cleaned_of_control_characters_and_edge_apostrophes():
    names = excel_export.get_workbook_sheet_names([worksheet_export(["a"], sheet_name="S\x01'"), worksheet_export(["a"], sheet_name="'Q1'")])
    data = excel_export.build_workbook([worksheet_export(["a"], sheet_name="S\x01'"), worksheet_export(["a"], sheet_name="'Q1'")])
    assert load(data).sheetnames == names
    for title in names:
        assert "\x01" not in title and not title.startswith("'") and not title.endswith("'")


# ----------------------------------------------------- database failure / rollback behaviour
def test_processing_and_export_survive_a_control_character_in_the_data(dirs, monkeypatch):
    upload = make_upload(dirs, CONTROL_CHAR_CSV)
    record = processing_service.process_uploaded_file(FakeDB(), upload)
    assert record.status == "COMPLETE"
    monkeypatch.setattr(export_service, "get_latest_result", lambda _db, _fid: record)
    result = export_service.export_uploaded_file(FakeDB(), upload)
    assert result.status == "COMPLETE"
    workbook = load_workbook(dirs / "exports" / Path(result.storage_key).name)
    texts = [c.value for ws in workbook.worksheets for row in ws.iter_rows() for c in row if isinstance(c.value, str)]
    assert any("�" in t for t in texts) and not any("\x0b" in t for t in texts)


def test_export_database_failure_removes_the_workbook_and_hides_driver_text(dirs, monkeypatch):
    upload = make_upload(dirs, CONTROL_CHAR_CSV)
    record = processing_service.process_uploaded_file(FakeDB(), upload)
    monkeypatch.setattr(export_service, "get_latest_result", lambda _db, _fid: record)
    before = set(exports_listing(dirs))
    db = FakeDB(fail_commit=True)
    with pytest.raises(ProcessingRequestError) as caught:
        export_service.export_uploaded_file(db, upload)
    assert caught.value.status_code == 503 and caught.value.code == "DATABASE_FAILURE"
    assert "SECRET123" not in caught.value.message and "SECRET123" not in str(caught.value)
    assert db.rollbacks == 1
    assert set(exports_listing(dirs)) == before  # no orphaned workbook


def test_unexpected_export_error_is_a_failed_export_not_a_server_error(dirs, monkeypatch):
    upload = make_upload(dirs, CONTROL_CHAR_CSV)
    record = processing_service.process_uploaded_file(FakeDB(), upload)
    monkeypatch.setattr(export_service, "get_latest_result", lambda _db, _fid: record)

    def boom(*_a, **_k):
        raise ValueError("cell content: ACME-secret-row")

    monkeypatch.setattr(excel_export, "build_workbook", boom)
    db = FakeDB()
    result = export_service.export_uploaded_file(db, upload)
    assert result.status == "FAILED" and db.commits == 1
    assert "ACME-secret-row" not in (result.error_message or "")


def test_processing_database_failure_removes_the_cleaned_csv(dirs):
    upload = make_upload(dirs, CONTROL_CHAR_CSV)
    before = set(exports_listing(dirs))
    db = FakeDB(fail_commit=True)
    with pytest.raises(ProcessingRequestError) as caught:
        processing_service.process_uploaded_file(db, upload)
    assert caught.value.status_code == 503 and caught.value.code == "DATABASE_FAILURE"
    assert db.rollbacks == 1
    assert set(exports_listing(dirs)) == before


def test_unexpected_processing_error_is_a_failed_run_and_leaves_no_artifacts(dirs, monkeypatch):
    upload = make_upload(dirs, two_sheet_xlsx(), name="m.xlsx", file_type="xlsx")
    original = data_quality.infer_column_type
    calls = {"n": 0}

    def flaky(series):
        calls["n"] += 1
        if calls["n"] > 3:  # sheet "One" finishes (3 columns); sheet "Two" explodes
            raise ZeroDivisionError("row 'ACME,5000' exploded")
        return original(series)

    monkeypatch.setattr(data_quality, "infer_column_type", flaky)
    before = set(exports_listing(dirs))
    record = processing_service.process_uploaded_file(FakeDB(), upload)
    assert record.status == "FAILED" and record.worksheets == []
    assert "ACME" not in (record.error_message or "")
    assert set(exports_listing(dirs)) == before  # sheet One's cleaned CSV was removed


def test_db_safety_still_raises_the_503_when_rollback_and_cleanup_both_fail():
    class BadRollback(FakeDB):
        def rollback(self):
            raise RuntimeError("rollback failed")

    with pytest.raises(ProcessingRequestError) as caught:
        db_safety.commit_or_cleanup(
            BadRollback(fail_commit=True), object(), error_cls=ProcessingRequestError, cleanup=lambda: 1 / 0
        )
    assert caught.value.status_code == 503 and "SECRET123" not in caught.value.message


# ------------------------------------------------------------------ paths, names, uploads
def test_artifact_deleter_cannot_reach_outside_the_exports_directory(dirs):
    victim = dirs / "victim.txt"
    victim.write_text("keep")
    file_processing.delete_export_artifacts(["exports/../victim.txt", "../victim.txt", "/etc/hostname", ""])
    assert victim.exists()


def test_cleaned_csv_reader_only_uses_the_file_name_part_of_a_key(dirs):
    (dirs / "outside.csv").write_text("a\nsecret\n")
    (dirs / "exports" / "inside.csv").write_text("a\nok\n")
    assert export_service._read_cleaned_df("exports/../outside.csv") is None
    assert export_service._read_cleaned_df("exports/inside.csv")["a"].tolist() == ["ok"]


def test_export_file_name_always_fits_the_255_character_column():
    name = build_export_filename("a" * 255)
    assert len(name) <= 255 and name.endswith("-export.xlsx")
    assert build_export_filename("q.csv") == "q.csv-export.xlsx"


def test_a_255_character_upload_name_still_gets_a_storable_export_name(dirs, monkeypatch):
    upload = make_upload(dirs, CONTROL_CHAR_CSV, name="a" * 255)
    record = processing_service.process_uploaded_file(FakeDB(), upload)
    monkeypatch.setattr(export_service, "get_latest_result", lambda _db, _fid: record)
    result = export_service.export_uploaded_file(FakeDB(), upload)
    assert result.status == "COMPLETE"
    assert len(result.original_filename) <= 255 and result.original_filename.endswith("-export.xlsx")


def test_download_file_name_cannot_break_out_of_the_header():
    cleaned = safe_download_filename('a";b\r\nX-Evil: 1/..\\c.xlsx')
    assert not any(ch in cleaned for ch in ('"', ";", "\r", "\n", "/", "\\"))
    assert safe_download_filename('"";') == "export.xlsx"
    assert safe_download_filename(None) == "export.xlsx"


class FakeUpload:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)
        self.bytes_read = 0

    async def read(self, n: int = -1) -> bytes:
        chunk = self.buffer.read(n)
        self.bytes_read += len(chunk)
        return chunk


def test_oversized_upload_is_refused_without_reading_the_whole_body():
    upload = FakeUpload(b"x" * 1_000_000)
    with pytest.raises(FileIntakeError) as caught:
        asyncio.run(read_upload_limited(upload, 1000))
    assert caught.value.code == "FILE_TOO_LARGE"
    assert upload.bytes_read <= 70_000


def test_upload_exactly_at_the_limit_is_accepted():
    assert asyncio.run(read_upload_limited(FakeUpload(b"y" * 1000), 1000)) == b"y" * 1000
    assert asyncio.run(read_upload_limited(FakeUpload(b""), 10)) == b""


# ----------------------------------------------------------- request size + security headers
async def call_asgi(app, *, headers=(), chunks=(b"",), method="POST", path="/api/files"):
    sent: list[dict] = []
    queue = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]

    async def receive():
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": method, "path": path, "headers": [(k.encode(), v.encode()) for k, v in headers]}
    await app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, dict(next(m["headers"] for m in sent if m["type"] == "http.response.start")), body


def draining_app(counter: dict):
    async def app(scope, receive, send):
        counter["called"] = counter.get("called", 0) + 1
        while True:
            message = await receive()
            if message["type"] != "http.request" or not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return app


RULE = lambda _scope: (100, "TOO_BIG", "Too big.")  # noqa: E731


def test_declared_oversize_is_refused_before_the_app_runs():
    counter: dict = {}
    app = RequestSizeLimitMiddleware(draining_app(counter), RULE)
    status, _headers, body = asyncio.run(call_asgi(app, headers=[("content-length", "101")], chunks=(b"x" * 101,)))
    assert status == 413 and counter.get("called") is None
    assert json.loads(body) == {"detail": {"code": "TOO_BIG", "message": "Too big."}}


def test_a_lying_content_length_is_still_caught_while_streaming():
    app = RequestSizeLimitMiddleware(draining_app({}), RULE)
    status, *_ = asyncio.run(call_asgi(app, headers=[("content-length", "10")], chunks=(b"x" * 60, b"x" * 60)))
    assert status == 413


def test_chunked_oversize_wins_even_if_the_app_turns_the_failure_into_its_own_400():
    async def app_with_own_400(scope, receive, send):
        while (await receive())["type"] == "http.request":
            pass
        await send({"type": "http.response.start", "status": 400, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    status, *_ = asyncio.run(call_asgi(RequestSizeLimitMiddleware(app_with_own_400, RULE), chunks=(b"x" * 60, b"x" * 60)))
    assert status == 413


def test_an_app_that_swallows_the_failure_and_sends_nothing_still_gets_a_413():
    async def silent_app(scope, receive, send):
        await receive()
        await receive()

    status, *_ = asyncio.run(call_asgi(RequestSizeLimitMiddleware(silent_app, RULE), chunks=(b"x" * 60, b"x" * 60)))
    assert status == 413


def test_bodies_at_the_limit_pass_and_one_byte_over_is_refused():
    app = RequestSizeLimitMiddleware(draining_app({}), RULE)
    assert asyncio.run(call_asgi(app, headers=[("content-length", "100")], chunks=(b"x" * 100,)))[0] == 200
    assert asyncio.run(call_asgi(app, chunks=(b"x" * 100,)))[0] == 200
    assert asyncio.run(call_asgi(app, chunks=(b"x" * 101,)))[0] == 413


def test_no_rule_means_no_limit_and_non_http_scopes_pass_through():
    counter: dict = {}
    app = RequestSizeLimitMiddleware(draining_app(counter), lambda _scope: None)
    assert asyncio.run(call_asgi(app, chunks=(b"x" * 10_000,)))[0] == 200
    seen = []

    async def lifespan_app(scope, receive, send):
        seen.append(scope["type"])

    asyncio.run(RequestSizeLimitMiddleware(lifespan_app, RULE)({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]


def test_security_headers_are_added_but_never_override_the_apps_own():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"cache-control", b"max-age=5")]})
        await send({"type": "http.response.body", "body": b""})

    _status, headers, _body = asyncio.run(call_asgi(SecurityHeadersMiddleware(app), method="GET", path="/api/health"))
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert headers[b"cache-control"] == b"max-age=5"
    assert headers[b"x-frame-options"] == b"DENY" and headers[b"referrer-policy"] == b"no-referrer"


def test_security_headers_skip_configured_path_prefixes():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    _s, docs_headers, _b = asyncio.run(call_asgi(SecurityHeadersMiddleware(app), method="GET", path="/docs"))
    assert b"x-content-type-options" not in docs_headers


# --------------------------------------------------- error envelope, logging, secrets, repo
def test_error_envelope_shape_and_passthrough():
    own = {"code": "X", "message": "m"}
    assert error_envelope.envelope_for_http_error(404, own) == {"detail": own}
    assert error_envelope.error_body("A", "b") == {"detail": {"code": "A", "message": "b"}}
    wrapped = error_envelope.envelope_for_http_error(405, "Method Not Allowed: internal text")
    assert wrapped["detail"]["code"] == "HTTP_405" and "internal text" not in wrapped["detail"]["message"]


def test_a_bare_404_never_looks_like_a_not_found_empty_state():
    # The dashboard treats a 404 whose code contains NOT_FOUND as "nothing stored yet".
    assert "NOT_FOUND" not in error_envelope.code_for_status(404)


def _logging_calls():
    for path in APP_ROOT.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"logger", "logging"}
            ):
                yield path, node


def test_no_logging_call_prints_an_exception_object_or_its_text():
    names = {"exc", "e", "err", "error", "exception"}

    def is_exception_text(arg) -> bool:
        if isinstance(arg, ast.Name):
            return arg.id in names  # logger.error("...", exc)
        if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) and arg.func.id in {"str", "repr"}:
            return bool(arg.args) and is_exception_text(arg.args[0])  # str(exc)
        if isinstance(arg, ast.JoinedStr):
            return any(isinstance(v, ast.FormattedValue) and is_exception_text(v.value) for v in arg.values)
        return False

    offenders = [
        f"{path.relative_to(APP_ROOT)}:{node.lineno}"
        for path, node in _logging_calls()
        if any(is_exception_text(arg) for arg in [*node.args, *(k.value for k in node.keywords)])
    ]
    assert offenders == []


def test_logger_exception_is_limited_to_storage_cleanup_helpers():
    # logger.exception writes the full exception chain (which can quote data) into the log.
    allowed = {"market_storage.py", "pdf_extraction.py", "analysis_storage.py"}
    offenders = [
        f"{path.name}:{node.lineno}" for path, node in _logging_calls()
        if node.func.attr == "exception" and path.name not in allowed
    ]
    assert offenders == []


def test_the_settings_object_hides_api_keys_from_repr(monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "AVKEY-123456")
    monkeypatch.setenv("NEWS_API_KEY", "NEWSKEY-654321")
    monkeypatch.setenv("LLM_API_KEY", "LLMKEY-999")
    text = repr(Settings()) + str(Settings())
    for secret in ("AVKEY-123456", "NEWSKEY-654321", "LLMKEY-999"):
        assert secret not in text


def test_env_example_and_gitignore_keep_secrets_out_of_the_repo():
    env_lines = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    for line in env_lines:
        key, _, value = line.partition("=")
        if key.strip().endswith("_API_KEY"):
            assert value.strip() == "", f"{key} must be empty in .env.example"
    ignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in ignore and "backend/storage" in ignore
