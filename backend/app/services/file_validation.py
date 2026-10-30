"""Validate uploads before anything is written to disk.

Beginner view:
  We do not trust the name the browser sends. We check size, extension,
  a bit of the file contents, and (when present) the MIME type.

Technical view:
  Extension + content sniffing are required. MIME is supporting only
  because browsers often send application/octet-stream. XLSX is verified
  as a real Office Open XML package (ZIP + required parts), not just a
  ZIP-family `PK` prefix — a bare prefix check would accept any ZIP file
  (a renamed .docx, .jar, or arbitrary archive).
"""

import io
import zipfile
from pathlib import Path

from app.core.config import get_settings
from app.core.exceptions import FileIntakeError

ALLOWED_EXTENSIONS = {"xlsx", "csv", "pdf"}

ALLOWED_MIMES = {
    "xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/octet-stream",
        "application/vnd.ms-excel",
    },
    "csv": {
        "text/csv",
        "text/plain",
        "application/csv",
        "application/vnd.ms-excel",
        "application/octet-stream",
    },
    "pdf": {
        "application/pdf",
        "application/octet-stream",
    },
}

MAX_ORIGINAL_NAME_LENGTH = 255

# An XLSX workbook must contain these OOXML package parts. Presence of both
# is a much stronger signal than a `PK` prefix, without needing a heavy
# dependency (openpyxl belongs to Phase 2, not file intake).
REQUIRED_XLSX_PARTS = {"[Content_Types].xml", "xl/workbook.xml"}

# Guard against zip bombs: reject before fully inflating if the declared
# uncompressed size is absurd relative to any realistic uploaded workbook.
MAX_XLSX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


def display_filename(raw_name: str | None) -> str:
    """Keep only the final path component and strip control characters."""
    if not raw_name or not raw_name.strip():
        raise FileIntakeError("INVALID_FILENAME", "A file name is required.")
    name = Path(raw_name.replace("\\", "/")).name.strip()
    if not name or name in {".", ".."}:
        raise FileIntakeError("INVALID_FILENAME", "The file name is not valid.")
    cleaned = "".join(ch for ch in name if ch.isprintable() and ch not in {"/", "\\"})
    if not cleaned:
        raise FileIntakeError("INVALID_FILENAME", "The file name is not valid.")
    return cleaned[:MAX_ORIGINAL_NAME_LENGTH]


def detect_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in ALLOWED_EXTENSIONS:
        raise FileIntakeError(
            "UNSUPPORTED_FILE_TYPE",
            "Only XLSX, CSV, and PDF files are allowed.",
        )
    return suffix


def _is_valid_xlsx(content: bytes) -> bool:
    """Structural OOXML check: valid ZIP container with the parts a workbook
    must have. Never extracts to disk — only reads the in-memory archive's
    directory and verifies checksums via `testzip()`.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            if not REQUIRED_XLSX_PARTS.issubset(names):
                return False
            total_uncompressed = sum(info.file_size for info in archive.infolist())
            if total_uncompressed > MAX_XLSX_UNCOMPRESSED_BYTES:
                return False
            if archive.testzip() is not None:
                return False
    except zipfile.BadZipFile:
        return False
    return True


def sniff_kind(content: bytes) -> str | None:
    if content.startswith(b"%PDF"):
        return "pdf"
    if content.startswith(b"PK") and _is_valid_xlsx(content):
        return "xlsx"
    if not content or b"\x00" in content[:4096]:
        return None
    return "csv"


def validate_mime(file_type: str, content_type: str | None) -> str | None:
    if not content_type:
        return None
    mime = content_type.split(";")[0].strip().lower()
    if not mime:
        return None
    allowed = ALLOWED_MIMES[file_type]
    if mime not in allowed:
        raise FileIntakeError(
            "UNSUPPORTED_FILE_TYPE",
            "The file content type does not match an allowed XLSX, CSV, or PDF type.",
        )
    return mime


def validate_upload(*, filename: str | None, content_type: str | None, content: bytes) -> dict:
    settings = get_settings()
    original = display_filename(filename)
    file_type = detect_extension(original)

    if not content:
        raise FileIntakeError("EMPTY_FILE", "The uploaded file is empty.")
    if len(content) > settings.max_upload_bytes:
        raise FileIntakeError(
            "FILE_TOO_LARGE",
            f"The file exceeds the maximum size of {settings.max_upload_bytes} bytes.",
        )

    sniffed = sniff_kind(content)
    if sniffed != file_type:
        raise FileIntakeError(
            "UNSUPPORTED_FILE_TYPE",
            "The file contents do not match the declared XLSX, CSV, or PDF type.",
        )

    mime = validate_mime(file_type, content_type)
    return {
        "original_filename": original,
        "file_type": file_type,
        "mime_type": mime,
        "size_bytes": len(content),
    }
