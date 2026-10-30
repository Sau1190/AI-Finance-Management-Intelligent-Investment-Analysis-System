"""Orchestrates Phase 3 export: take Phase 2's already-persisted
ProcessingResult, re-read the original file and Phase 2's cleaned CSVs, and
hand real data to app.services.excel_export to format into a workbook.

This module computes nothing new about the data — no ratios, no scores, no
guessed values. It only reassembles what Phase 1/2 already produced into a
professional-looking export.
"""

import logging

import pandas as pd
from sqlalchemy.orm import Session

from app.core.exceptions import ProcessingRequestError
from app.models.export_result import ExportResult, ExportRunStatus
from app.models.uploaded_file import UploadedFile
from app.services import excel_export, file_processing, file_storage
from app.services.processing_service import get_latest_result

logger = logging.getLogger(__name__)


def _read_cleaned_df(storage_key: str) -> pd.DataFrame | None:
    """Read a Phase 2 cleaned CSV by its storage key. Returns None (not a
    raised error) if it can no longer be read — a missing cleaned file
    should not prevent exporting the raw data and summary that are still
    available.
    """
    path = file_processing.exports_directory() / storage_key.removeprefix("exports/")
    try:
        return pd.read_csv(path, dtype=str)
    except OSError:
        logger.warning("Cleaned data file missing for export: %s", storage_key)
        return None


def _build_worksheet_exports(
    uploaded_file: UploadedFile, worksheets: list[dict], content: bytes
) -> list[excel_export.WorksheetExport]:
    if uploaded_file.file_type == "xlsx":
        raw_by_sheet = file_processing.read_xlsx_worksheets(content)
    else:
        raw_df, _delimiter = file_processing.read_csv_raw(content)
        raw_by_sheet = {"csv": raw_df}

    exports: list[excel_export.WorksheetExport] = []
    for report in worksheets:
        columns = report.get("columns", [])
        missing_total = sum(c.get("missing_count", 0) for c in columns)
        inconsistent_total = sum(
            (c.get("inconsistent_values") or {}).get("count", 0) for c in columns
        )
        # Phase 2 renames a column's header to its canonical concept name in
        # the cleaned CSV (e.g. "Revenue" -> "revenue") when normalization
        # applied. column_types must be keyed by that FINAL header — the one
        # cleaned_df.columns actually contains — not the original source
        # name, or every normalized column's number formatting silently
        # never applies in the Cleaned sheet.
        column_types = {(c.get("canonical_concept") or c["name"]): c["inferred_type"] for c in columns}

        cleaned_df = None
        if report.get("cleaned_data_status") == "GENERATED" and report.get("cleaned_data_storage_key"):
            cleaned_df = _read_cleaned_df(report["cleaned_data_storage_key"])

        exports.append(
            excel_export.WorksheetExport(
                sheet_name=report["sheet_name"],
                row_count=report.get("row_count", 0),
                column_count=report.get("column_count", 0),
                missing_total=missing_total,
                duplicate_row_count=report.get("duplicate_row_count", 0),
                inconsistent_total=inconsistent_total,
                cleaned_data_status=report.get("cleaned_data_status", "SKIPPED"),
                warnings=report.get("warnings", []),
                errors=report.get("errors", []),
                raw_df=raw_by_sheet.get(report["sheet_name"]),
                header_row_index=report.get("header_row_index"),
                cleaned_df=cleaned_df,
                column_types=column_types,
            )
        )
    return exports


def export_uploaded_file(db: Session, uploaded_file: UploadedFile) -> ExportResult:
    """Build and persist a Phase 3 export workbook for a file's most recent
    processing result. Raises ProcessingRequestError (404) if the file has
    never been processed — export has nothing to reassemble without that.
    A failure to build/save the workbook itself is recorded as a FAILED
    ExportResult and still returned, not raised, mirroring how a failed
    processing run is a normal, inspectable outcome rather than a 500.
    """
    latest = get_latest_result(db, uploaded_file.id)
    if latest is None:
        raise ProcessingRequestError(
            "PROCESSING_RESULT_NOT_FOUND",
            "This file has not been processed yet. Run processing before exporting.",
            status_code=404,
        )

    try:
        if latest.status == "FAILED":
            content_bytes = excel_export.build_workbook(
                [], processing_failed_note=latest.error_message or "Processing did not complete for this file."
            )
            sheet_names = ["Summary"]
        else:
            directory = file_storage.upload_directory()
            try:
                original_content = (directory / uploaded_file.stored_filename).read_bytes()
            except OSError as exc:
                raise ProcessingRequestError(
                    "FILE_UNAVAILABLE",
                    "The original uploaded file could not be found in storage.",
                    status_code=500,
                ) from exc

            try:
                worksheet_exports = _build_worksheet_exports(uploaded_file, latest.worksheets, original_content)
            except file_processing.UnreadableFileError as exc:
                raise ProcessingRequestError(
                    "FILE_UNAVAILABLE",
                    "The original uploaded file could not be read for export.",
                    status_code=500,
                ) from exc
            content_bytes = excel_export.build_workbook(worksheet_exports)
            sheet_names = excel_export.get_workbook_sheet_names(worksheet_exports)

        stored_filename, storage_key = file_processing.save_export_workbook(content_bytes)
    except ProcessingRequestError as exc:
        if exc.code == "PROCESSING_RESULT_NOT_FOUND":
            raise
        logger.exception("Export failed for file %s", uploaded_file.id)
        record = ExportResult(
            file_id=uploaded_file.id,
            processing_result_id=latest.id,
            status=ExportRunStatus.FAILED.value,
            error_message=exc.message,
            sheet_names=[],
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    record = ExportResult(
        file_id=uploaded_file.id,
        processing_result_id=latest.id,
        status=ExportRunStatus.COMPLETE.value,
        storage_key=storage_key,
        original_filename=f"{uploaded_file.original_filename}-export.xlsx",
        sheet_names=sheet_names,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_latest_export(db: Session, file_id: str) -> ExportResult | None:
    return (
        db.query(ExportResult)
        .filter(ExportResult.file_id == file_id)
        .order_by(ExportResult.created_at.desc())
        .first()
    )
