"""Orchestrates the Phase 2 processing pipeline: read -> detect header ->
infer types -> quality checks -> normalize -> write cleaned data -> persist.

Kept deliberately procedural (one function per pipeline stage, called in
sequence) rather than a class hierarchy — there is one pipeline, not a
family of interchangeable ones, so a class-based abstraction would be
premature.
"""

import logging

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ProcessingRequestError
from app.models.processing_result import ProcessingResult, ProcessingRunStatus
from app.models.uploaded_file import UploadedFile
from app.services import data_quality, file_processing, file_storage
from app.services.financial_normalization import build_normalization_mapping

logger = logging.getLogger(__name__)

PROCESSABLE_FILE_TYPES = {"xlsx", "csv"}


def _process_sheet(sheet_name: str, raw: pd.DataFrame, *, csv_delimiter: str | None = None) -> dict:
    """Run the full quality/normalization pipeline on one raw (header-less)
    grid and return a report dict matching schemas.processing.WorksheetReport.
    """
    settings = get_settings()
    report: dict = {
        "sheet_name": sheet_name,
        "is_empty": False,
        "header_row_index": None,
        "header_assumed_default": False,
        "row_count": 0,
        "column_count": 0,
        "columns": [],
        "duplicate_row_count": 0,
        "normalization_mappings": {},
        "ambiguous_mappings": [],
        "warnings": [],
        "errors": [],
        "cleaned_data_status": "SKIPPED",
        "cleaned_data_storage_key": None,
        "csv_delimiter": csv_delimiter,
    }

    if file_processing.is_blank_grid(raw):
        report["is_empty"] = True
        report["warnings"].append("Worksheet contains no data.")
        return report

    total_rows = len(raw)
    if total_rows > settings.max_processing_rows:
        report["row_count"] = total_rows
        report["column_count"] = raw.shape[1]
        report["errors"].append(
            f"DATASET_TOO_LARGE: {total_rows} rows exceeds the processing limit of "
            f"{settings.max_processing_rows}. Not processed."
        )
        return report

    header_index, assumed_default = data_quality.detect_header_row(raw)
    report["header_row_index"] = header_index
    report["header_assumed_default"] = assumed_default
    if assumed_default:
        report["warnings"].append("Header row could not be confidently detected; assumed the first row.")

    header_values = raw.iloc[header_index].tolist()
    column_names: list[str] = []
    seen: dict[str, int] = {}
    for position, value in enumerate(header_values):
        name = str(value).strip() if pd.notna(value) and str(value).strip() else f"column_{position + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        column_names.append(name)

    data = raw.iloc[header_index + 1 :].reset_index(drop=True)
    data.columns = column_names
    row_count = len(data)
    report["row_count"] = row_count
    report["column_count"] = len(column_names)

    if row_count == 0:
        report["warnings"].append("Worksheet has a header row but no data rows.")
        return report

    columns_report = []
    for name in column_names:
        series = data[name]
        column_type = data_quality.infer_column_type(series)
        missing = data_quality.count_missing_values(series)
        inconsistency = data_quality.find_inconsistent_values(series, column_type)
        columns_report.append(
            {
                "name": name,
                "inferred_type": column_type,
                "missing_count": missing,
                "canonical_concept": None,
                "inconsistent_values": inconsistency,
            }
        )

    report["duplicate_row_count"] = data_quality.count_duplicate_rows(data)

    mapping, ambiguous = build_normalization_mapping(column_names)
    for column in columns_report:
        if column["name"] in mapping:
            column["canonical_concept"] = mapping[column["name"]]
    report["columns"] = columns_report
    report["normalization_mappings"] = mapping
    report["ambiguous_mappings"] = ambiguous
    if ambiguous:
        report["warnings"].append(
            "Some columns matched more than one financial concept and were left unrenamed: "
            + ", ".join(a["canonical_concept"] for a in ambiguous)
        )

    cleaned = data.rename(columns=mapping)
    try:
        _, storage_key = file_processing.save_cleaned_csv(cleaned)
        report["cleaned_data_status"] = "GENERATED"
        report["cleaned_data_storage_key"] = storage_key
    except ProcessingRequestError as exc:
        logger.exception("Failed to write cleaned data for sheet %s", sheet_name)
        report["cleaned_data_status"] = "FAILED"
        report["errors"].append(exc.message)

    return report


def process_uploaded_file(db: Session, uploaded_file: UploadedFile) -> ProcessingResult:
    """Run the Phase 2 pipeline for one uploaded file and persist the result.
    Never mutates the original stored file. A file that cannot be parsed at
    all yields a FAILED ProcessingResult, not an exception — that is a valid
    outcome the caller should be able to inspect, not a server error.
    """
    if uploaded_file.file_type not in PROCESSABLE_FILE_TYPES:
        raise ProcessingRequestError(
            "UNSUPPORTED_FILE_TYPE",
            "Only XLSX and CSV files can be processed in this phase.",
            status_code=400,
        )

    directory = file_storage.upload_directory()
    original_path = directory / uploaded_file.stored_filename
    try:
        content = original_path.read_bytes()
    except OSError as exc:
        raise ProcessingRequestError(
            "FILE_UNAVAILABLE",
            "The original uploaded file could not be found in storage.",
            status_code=500,
        ) from exc

    worksheets: list[dict] = []
    status = ProcessingRunStatus.COMPLETE.value
    error_message: str | None = None

    try:
        if uploaded_file.file_type == "xlsx":
            sheets = file_processing.read_xlsx_worksheets(content)
            for sheet_name, raw in sheets.items():
                worksheets.append(_process_sheet(sheet_name, raw))
        else:
            raw, delimiter = file_processing.read_csv_raw(content)
            worksheets.append(_process_sheet("csv", raw, csv_delimiter=delimiter))
    except file_processing.UnreadableFileError as exc:
        logger.exception("Could not read uploaded file %s for processing", uploaded_file.id)
        status = ProcessingRunStatus.FAILED.value
        error_message = "The file could not be read. It may be corrupted or use an unsupported structure."
        worksheets = []

    # Original file is only ever opened for reading above — never written to.
    record = ProcessingResult(
        file_id=uploaded_file.id,
        status=status,
        error_message=error_message,
        worksheets=worksheets,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_latest_result(db: Session, file_id: str) -> ProcessingResult | None:
    return (
        db.query(ProcessingResult)
        .filter(ProcessingResult.file_id == file_id)
        .order_by(ProcessingResult.created_at.desc())
        .first()
    )
