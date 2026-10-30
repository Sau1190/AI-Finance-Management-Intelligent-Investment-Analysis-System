"""Extract text and tables from uploaded PDFs.

Beginner view:
  This is the "open the PDF and read what's literally there" step — no
  guessing, no OCR, no financial interpretation. Later phases will read
  the structured result this module produces.

Technical view:
  PyMuPDF (import name `pymupdf`, not the deprecated `fitz` alias) opens
  the file, iterates pages, and extracts text + tables via
  Page.find_tables(). Extracted text/tables are written to
  storage/extracts/ under generated names, mirroring file_processing.py's
  never-overwrite guarantee for Phase 2/3's generated artifacts.
"""

import csv
import io
import logging
from pathlib import Path
from uuid import uuid4

import pymupdf

from app.core.config import get_settings
from app.core.exceptions import ExtractionRequestError

logger = logging.getLogger(__name__)


class UnreadablePdfError(Exception):
    """The PDF could not be opened/parsed at all. Carries no internals in
    str() that are safe to show a user unmodified — callers decide the
    user-facing message.
    """


class EncryptedPdfError(Exception):
    """The PDF requires a password. We never attempt to guess one."""


def extracts_directory() -> Path:
    path = Path(get_settings().extracts_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_unique(content: str, suffix: str, failure_message: str) -> tuple[str, str]:
    """Write `content` to storage/extracts/ under a unique generated name.
    Never overwrites (exclusive create). If the write fails part-way, the
    partially written file is removed before the error is raised, so a
    failed write never leaves a truncated artifact behind. Returns
    (stored_filename, storage_key).
    """
    directory = extracts_directory()
    for _ in range(5):
        stored_filename = f"{uuid4().hex}{suffix}"
        destination = directory / stored_filename
        try:
            with destination.open("x", encoding="utf-8", newline="") as handle:
                handle.write(content)
        except FileExistsError:
            continue
        except OSError as exc:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                logger.exception("Could not remove partially written artifact %s", stored_filename)
            raise ExtractionRequestError(
                "EXTRACTION_STORAGE_FAILURE", failure_message, status_code=500
            ) from exc
        return stored_filename, f"extracts/{stored_filename}"
    raise ExtractionRequestError(
        "EXTRACTION_STORAGE_FAILURE",
        "Could not generate a unique filename for an extracted artifact.",
        status_code=500,
    )


def save_text(text: str) -> tuple[str, str]:
    """Write one page's extracted text to storage/extracts/ under a unique
    generated name. Never overwrites. Returns (stored_filename, storage_key).
    """
    return _write_unique(text, ".txt", "The extracted text could not be saved.")


def save_table_csv(rows: list[list[str | None]]) -> tuple[str, str]:
    """Write one extracted table's rows to storage/extracts/ as CSV under a
    unique generated name. Never overwrites.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row in rows:
        writer.writerow(["" if cell is None else cell for cell in row])
    return _write_unique(buffer.getvalue(), ".csv", "An extracted table could not be saved.")


def delete_artifacts(storage_keys: list[str]) -> list[str]:
    """Best-effort removal of generated artifacts by storage key, used to
    roll back a failed extraction run. Never raises: returns the keys that
    could not be removed (already logged) so the caller can still finish
    recording the failure. Only the file name component of each key is used,
    so a key can never address anything outside the extracts directory.
    """
    directory = extracts_directory()
    not_removed: list[str] = []
    for key in storage_keys:
        try:
            (directory / Path(key).name).unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove extraction artifact %s", Path(key).name)
            not_removed.append(key)
    return not_removed


def open_pdf(content: bytes) -> "pymupdf.Document":
    """Open PDF bytes for reading. Raises EncryptedPdfError if a password is
    required (we never attempt to guess one — that would not be
    deterministic/safe behavior), UnreadablePdfError if the file cannot be
    parsed at all (Phase 1 already confirmed the extension/content-sniff
    looked like a PDF, but that does not guarantee PyMuPDF can parse it).
    """
    try:
        doc = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 — any parser failure is "unreadable" to us
        raise UnreadablePdfError(str(exc)) from exc
    if doc.needs_pass:
        doc.close()
        raise EncryptedPdfError("This PDF is password-protected.")
    return doc


def extract_page(page: "pymupdf.Page") -> dict:
    """Extract one page's literal text and tables. Never raises for a page
    with no text or no detectable tables — those are normal outcomes,
    reported via warnings, not errors. Table detection is best-effort and
    failing it never blocks text extraction for the same page.
    """
    text = page.get_text() or ""
    warnings: list[str] = []
    if not text.strip():
        warnings.append(
            "No extractable text on this page. It may be a scanned image; OCR is not performed in this phase."
        )

    tables: list[list[list[str | None]]] = []
    try:
        table_finder = page.find_tables()
        for table in table_finder.tables:
            tables.append(table.extract())
    except Exception:  # noqa: BLE001 — table detection is best-effort, never fatal to the page
        warnings.append("Table detection failed for this page; text extraction above is unaffected.")

    return {"text": text, "warnings": warnings, "tables": tables}
