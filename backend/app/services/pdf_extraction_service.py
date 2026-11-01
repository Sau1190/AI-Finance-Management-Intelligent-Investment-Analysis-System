"""Orchestrates the Phase 4 PDF extraction pipeline: open -> per-page text +
table extraction -> write full text/tables to storage -> persist a
structured, bounded-preview result.

Kept deliberately procedural, mirroring processing_service.py's style —
one pipeline, not a family of interchangeable ones.
"""

import logging

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ExtractionRequestError
from app.models.pdf_extraction_result import ExtractionRunStatus, PdfExtractionResult
from app.models.uploaded_file import UploadedFile
from app.services import file_storage, pdf_extraction

logger = logging.getLogger(__name__)

EXTRACTABLE_FILE_TYPES = {"pdf"}
TEXT_PREVIEW_CHARS = 500
TABLE_PREVIEW_ROWS = 5


def _build_page_report(page_number: int, extracted: dict, written_keys: list[str]) -> dict:
    """Build one page's report, writing its full text and table artifacts.

    Saved artifacts are REQUIRED: a report that references a storage key must
    point at a file that exists, and a page with text or tables must not
    silently lose them. So a storage failure is not downgraded to a warning —
    ExtractionRequestError propagates and the caller fails the whole run.
    Every key is appended to `written_keys` the moment its file is saved so
    the caller can roll back everything written so far.
    """
    text = extracted["text"]
    warnings = list(extracted["warnings"])
    char_count = len(text)

    text_storage_key = None
    if text.strip():
        _, text_storage_key = pdf_extraction.save_text(text)
        written_keys.append(text_storage_key)

    tables_report = []
    for index, rows in enumerate(extracted["tables"]):
        row_count = len(rows)
        column_count = len(rows[0]) if rows else 0
        _, table_key = pdf_extraction.save_table_csv(rows)
        written_keys.append(table_key)
        tables_report.append(
            {
                "table_index": index,
                "row_count": row_count,
                "column_count": column_count,
                "preview_rows": rows[:TABLE_PREVIEW_ROWS],
                "storage_key": table_key,
            }
        )

    return {
        "page_number": page_number,
        "char_count": char_count,
        "text_preview": text[:TEXT_PREVIEW_CHARS],
        "text_storage_key": text_storage_key,
        "table_count": len(tables_report),
        "tables": tables_report,
        "warnings": warnings,
    }


def extract_pdf(db: Session, uploaded_file: UploadedFile) -> PdfExtractionResult:
    """Run the Phase 4 pipeline for one uploaded PDF and persist the result.
    Never mutates the original stored file. A PDF that cannot be read at all
    (corrupt, encrypted, or exceeding the page-count limit) yields a FAILED
    PdfExtractionResult, not an exception — that is a valid, inspectable
    outcome, not a server error.

    Completeness rule: a result is COMPLETE only if every artifact it
    describes was saved. If saving any page's text or any table fails (or
    page extraction fails unexpectedly), the run is all-or-nothing: the
    result is FAILED with no pages, and every artifact already written during
    this run is deleted, so no orphaned or half-described output remains.
    """
    if uploaded_file.file_type not in EXTRACTABLE_FILE_TYPES:
        raise ExtractionRequestError(
            "UNSUPPORTED_FILE_TYPE",
            "Only PDF files can be extracted in this phase.",
            status_code=400,
        )

    directory = file_storage.upload_directory()
    original_path = directory / uploaded_file.stored_filename
    try:
        content = original_path.read_bytes()
    except OSError as exc:
        raise ExtractionRequestError(
            "FILE_UNAVAILABLE",
            "The original uploaded file could not be found in storage.",
            status_code=500,
        ) from exc

    settings = get_settings()
    status = ExtractionRunStatus.COMPLETE.value
    error_message: str | None = None
    page_count = 0
    pages: list[dict] = []

    written_keys: list[str] = []
    failure_message: str | None = None

    doc = None
    try:
        doc = pdf_extraction.open_pdf(content)
    except pdf_extraction.EncryptedPdfError:
        status = ExtractionRunStatus.FAILED.value
        error_message = "This PDF is password-protected and cannot be extracted."
    except pdf_extraction.UnreadablePdfError as exc:
        logger.error("Could not read uploaded file %s for extraction: %s", uploaded_file.id, type(exc).__name__)
        status = ExtractionRunStatus.FAILED.value
        error_message = "The PDF could not be read. It may be corrupted or use an unsupported structure."

    if doc is not None:
        try:
            page_count = doc.page_count
            if page_count > settings.max_pdf_pages:
                status = ExtractionRunStatus.FAILED.value
                error_message = (
                    f"PDF_TOO_LARGE: {page_count} pages exceeds the extraction limit of "
                    f"{settings.max_pdf_pages}. Not extracted."
                )
            else:
                page_number = 0
                try:
                    for index in range(page_count):
                        page_number = index + 1
                        extracted = pdf_extraction.extract_page(doc[index])
                        pages.append(_build_page_report(page_number, extracted, written_keys))
                except ExtractionRequestError as exc:
                    logger.error("Storage failure while extracting page %s of file %s: %s", page_number, uploaded_file.id, exc.code)
                    failure_message = (
                        f"EXTRACTION_STORAGE_FAILURE: could not save extracted content for page "
                        f"{page_number}. No extraction results were kept."
                    )
                except Exception as exc:  # noqa: BLE001 — never leave a half-written run behind
                    logger.error("Unexpected failure while extracting page %s of file %s: %s", page_number, uploaded_file.id, type(exc).__name__)
                    failure_message = (
                        f"The PDF could not be fully extracted (failed on page {page_number}). "
                        "No extraction results were kept."
                    )
        finally:
            # Original file is only ever opened for reading above — never written to.
            doc.close()

    if failure_message is not None:
        status = ExtractionRunStatus.FAILED.value
        error_message = failure_message
        pages = []
        pdf_extraction.delete_artifacts(written_keys)
        written_keys = []

    record = PdfExtractionResult(
        file_id=uploaded_file.id,
        status=status,
        error_message=error_message,
        page_count=page_count,
        pages=pages,
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        # The result row was not saved, so nothing may reference the artifacts
        # written for it — remove them rather than leave orphans on disk.
        db.rollback()
        pdf_extraction.delete_artifacts(written_keys)
        raise
    return record


def get_latest_result(db: Session, file_id: str) -> PdfExtractionResult | None:
    return (
        db.query(PdfExtractionResult)
        .filter(PdfExtractionResult.file_id == file_id)
        .order_by(PdfExtractionResult.created_at.desc())
        .first()
    )
