"""Orchestrates Phase 5 fundamental analysis: take the latest Phase 2
ProcessingResult, read each worksheet's cleaned CSV, compute metrics with
app.services.fundamental_metrics, save per-row metric CSVs, and persist a
structured, explainable result.

Completeness rule (same as Phase 4): a result is COMPLETE only if every
artifact it references was saved. A storage failure, or an unexpected failure
while analyzing a worksheet, fails the whole run (no worksheets reported) and
deletes whatever artifacts that run already wrote.
"""

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.core.exceptions import AnalysisRequestError
from app.models.fundamental_analysis_result import AnalysisRunStatus, FundamentalAnalysisResult
from app.models.uploaded_file import UploadedFile
from app.services import analysis_storage, file_processing, fundamental_metrics
from app.services.processing_service import get_latest_result as get_latest_processing_result

logger = logging.getLogger(__name__)

ANALYZABLE_FILE_TYPES = {"xlsx", "csv"}


def _read_cleaned_df(storage_key: str) -> pd.DataFrame | None:
    """Read a Phase 2 cleaned CSV by storage key (file-name part only, so a
    key can never point outside the exports directory). None if unreadable.
    """
    path = file_processing.exports_directory() / Path(storage_key).name
    try:
        # Only truly blank cells are "missing". pandas' default would also turn
        # literal text such as "n/a", "NA" or "null" into NaN, silently
        # relabelling a non-numeric value as missing and disagreeing with
        # Phase 2, which counts only blanks as missing.
        return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
        logger.warning("Cleaned data file could not be read for analysis: %s", Path(storage_key).name)
        return None


def _skipped_sheet(name: str, reason: str, row_count: int = 0) -> dict:
    return {
        "sheet_name": name,
        "status": "SKIPPED",
        "reason": reason,
        "row_count": row_count,
        "recognized_concepts": [],
        "entity_column": None,
        "date_column": None,
        "metrics": [],
        "warnings": [],
        "preview_rows": [],
        "metrics_storage_key": None,
    }


def _analyze_worksheet(processing_report: dict, written_keys: list[str]) -> dict:
    name = processing_report.get("sheet_name", "")
    row_count = int(processing_report.get("row_count", 0) or 0)

    if processing_report.get("is_empty"):
        return _skipped_sheet(name, "The worksheet has no data.", row_count)
    key = processing_report.get("cleaned_data_storage_key")
    cleaned_status = processing_report.get("cleaned_data_status")
    if cleaned_status != "GENERATED" or not key:
        return _skipped_sheet(
            name,
            f"No cleaned data is available for this worksheet (cleaned data status: {cleaned_status}).",
            row_count,
        )
    df = _read_cleaned_df(key)
    if df is None:
        return _skipped_sheet(name, "The cleaned data file could not be read.", row_count)

    sheet_report, csv_text = fundamental_metrics.analyze_sheet(
        df, processing_report.get("ambiguous_mappings", [])
    )
    sheet_report["sheet_name"] = name
    sheet_report["metrics_storage_key"] = None
    if csv_text is not None:
        _, storage_key = analysis_storage.save_metrics_csv(csv_text)
        written_keys.append(storage_key)
        sheet_report["metrics_storage_key"] = storage_key
    return sheet_report


def analyze_fundamentals(db: Session, uploaded_file: UploadedFile) -> FundamentalAnalysisResult:
    """Run Phase 5 for one uploaded Excel/CSV file using its latest Phase 2
    processing result, and persist the outcome. Never touches the original
    upload or Phase 2's cleaned files. A run that cannot analyze anything
    (processing failed, storage failed) is a FAILED result, not an exception.
    """
    if uploaded_file.file_type not in ANALYZABLE_FILE_TYPES:
        raise AnalysisRequestError(
            "UNSUPPORTED_FILE_TYPE",
            "Fundamental analysis needs an Excel or CSV file that has been processed.",
            status_code=400,
        )
    processing = get_latest_processing_result(db, uploaded_file.id)
    if processing is None:
        raise AnalysisRequestError(
            "PROCESSING_RESULT_NOT_FOUND",
            "This file has not been processed yet. Process it first, then run the analysis.",
            status_code=404,
        )

    status = AnalysisRunStatus.COMPLETE.value
    error_message: str | None = None
    worksheets: list[dict] = []
    written_keys: list[str] = []

    if processing.status != "COMPLETE":
        status = AnalysisRunStatus.FAILED.value
        error_message = (
            "The latest processing run did not complete, so there is nothing to analyze. "
            "Fix the file and process it again."
        )
    else:
        position = 0
        failure_message: str | None = None
        try:
            for position, processing_report in enumerate(processing.worksheets, start=1):
                worksheets.append(_analyze_worksheet(processing_report, written_keys))
        except AnalysisRequestError:
            logger.exception("Storage failure analyzing worksheet %s of file %s", position, uploaded_file.id)
            failure_message = (
                f"ANALYSIS_STORAGE_FAILURE: could not save analysis metrics for worksheet #{position}. "
                "No analysis results were kept."
            )
        except Exception:  # noqa: BLE001 — never leave a half-written run behind
            logger.exception("Unexpected failure analyzing worksheet %s of file %s", position, uploaded_file.id)
            failure_message = (
                f"The analysis failed on worksheet #{position}. No analysis results were kept."
            )
        if failure_message is not None:
            status = AnalysisRunStatus.FAILED.value
            error_message = failure_message
            worksheets = []
            analysis_storage.delete_artifacts(written_keys)
            written_keys = []

    record = FundamentalAnalysisResult(
        file_id=uploaded_file.id,
        processing_result_id=processing.id,
        status=status,
        error_message=error_message,
        worksheets=worksheets,
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        analysis_storage.delete_artifacts(written_keys)
        raise
    return record


def get_latest_result(db: Session, file_id: str) -> FundamentalAnalysisResult | None:
    return (
        db.query(FundamentalAnalysisResult)
        .filter(FundamentalAnalysisResult.file_id == file_id)
        .order_by(FundamentalAnalysisResult.created_at.desc())
        .first()
    )
