"""Read uploaded XLSX/CSV files into raw (header-less) DataFrames.

Beginner view:
  This is the "open the file" step. We don't assume a header row here —
  that decision belongs to data_quality.detect_header_row, working on the
  raw grid this module returns.

Technical view:
  XLSX: openpyxl via pandas.read_excel(sheet_name=None, header=None) to get
  every worksheet as a raw grid. CSV: read as text, sniff a delimiter from a
  small set of candidates, then pandas.read_csv(header=None).
"""

import csv
import io
import logging
from pathlib import Path
from uuid import uuid4

import pandas as pd

from app.core.config import get_settings
from app.core.exceptions import ProcessingRequestError

logger = logging.getLogger(__name__)

CANDIDATE_CSV_DELIMITERS = [",", ";", "\t", "|"]
DEFAULT_CSV_DELIMITER = ","
SNIFF_SAMPLE_BYTES = 8192


class UnreadableFileError(Exception):
    """The file could not be parsed at all. Carries no internals in str()
    that would be safe to show a user unmodified — callers decide the
    user-facing message.
    """


def read_xlsx_worksheets(content: bytes) -> dict[str, pd.DataFrame]:
    """Return {worksheet_name: raw_dataframe} for every worksheet, in
    workbook order. Raw = no header assumed (header=None), values preserved
    as read. Raises UnreadableFileError if the workbook cannot be opened at
    all (Phase 1 already confirmed it's structurally a real OOXML package,
    but that does not guarantee openpyxl can fully parse its contents).
    """
    try:
        sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None, engine="openpyxl")
    except Exception as exc:  # noqa: BLE001 — any parser failure is "unreadable" to us
        raise UnreadableFileError(str(exc)) from exc
    return sheets


def sniff_csv_delimiter(sample_text: str) -> str:
    """Best-effort delimiter detection among a fixed, safe candidate set.
    Falls back to comma — never guesses an arbitrary character.
    """
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters="".join(CANDIDATE_CSV_DELIMITERS))
        if dialect.delimiter in CANDIDATE_CSV_DELIMITERS:
            return dialect.delimiter
    except csv.Error:
        pass
    return DEFAULT_CSV_DELIMITER


def read_csv_raw(content: bytes) -> tuple[pd.DataFrame, str]:
    """Decode and parse CSV bytes into a raw (header=None) DataFrame.
    Returns (dataframe, detected_delimiter). Raises UnreadableFileError on
    decode or parse failure.

    Deliberately does NOT use pandas.read_csv(header=None, ...) directly:
    with no header, pandas infers the expected column count from the first
    physical row and silently drops (on_bad_lines="skip") every later row
    that doesn't match — which discards real data whenever a file starts
    with a short title/comment line before its actual header. Instead we
    parse with csv.reader and pad every row to the widest row's column
    count, so no row is ever silently dropped.
    """
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UnreadableFileError(str(exc)) from exc

    delimiter = sniff_csv_delimiter(text[:SNIFF_SAMPLE_BYTES])
    try:
        rows = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter) if row]
    except csv.Error as exc:
        raise UnreadableFileError(str(exc)) from exc

    if not rows:
        return pd.DataFrame(), delimiter

    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    df = pd.DataFrame(padded, dtype=str).replace("", pd.NA)
    return df, delimiter


def is_blank_grid(raw: pd.DataFrame) -> bool:
    """True if every cell is NaN, empty, or whitespace-only. Deliberately
    stricter than DataFrame.dropna(how="all") — a sheet of only blank
    strings should count as empty too, not just a sheet of true NaN.
    """
    if raw.empty:
        return True
    stripped = raw.astype(str).apply(lambda col: col.str.strip())
    lowered = stripped.apply(lambda col: col.str.lower())
    blank = raw.isna() | (stripped == "") | (lowered == "nan")
    return bool(blank.all().all())


def exports_directory() -> Path:
    path = Path(get_settings().exports_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def delete_export_artifacts(storage_keys: list[str]) -> list[str]:
    """Best-effort rollback of generated files in storage/exports/ (cleaned CSVs,
    workbooks). Never raises; returns the keys it could not remove. Only the
    file-name part of a key is used, so a key can never address anything
    outside the exports directory."""
    directory = exports_directory()
    not_removed: list[str] = []
    for key in storage_keys:
        if not key:
            continue
        try:
            (directory / Path(key).name).unlink(missing_ok=True)
        except OSError:
            logger.error("Could not remove generated artifact %s", Path(key).name)
            not_removed.append(key)
    return not_removed


def save_export_workbook(content: bytes) -> tuple[str, str]:
    """Write a generated export workbook's bytes to storage/exports/ under a
    unique generated name. Same never-overwrite guarantee as
    save_cleaned_csv. Returns (stored_filename, storage_key).
    """
    directory = exports_directory()
    for _ in range(5):
        stored_filename = f"{uuid4().hex}.xlsx"
        destination = directory / stored_filename
        if destination.exists():
            continue
        try:
            destination.write_bytes(content)
        except OSError as exc:
            raise ProcessingRequestError(
                "PROCESSING_STORAGE_FAILURE",
                "The export workbook could not be saved.",
                status_code=500,
            ) from exc
        return stored_filename, f"exports/{stored_filename}"
    raise ProcessingRequestError(
        "PROCESSING_STORAGE_FAILURE",
        "The export workbook could not be saved.",
        status_code=500,
    )


def save_cleaned_csv(df: pd.DataFrame) -> tuple[str, str]:
    """Write a cleaned/normalized DataFrame to storage/exports/ under a
    unique generated name. Never overwrites — same guarantee as original
    uploads in file_storage.py. Returns (stored_filename, storage_key).
    """
    directory = exports_directory()
    for _ in range(5):
        stored_filename = f"{uuid4().hex}.csv"
        destination = directory / stored_filename
        if destination.exists():
            continue
        try:
            df.to_csv(destination, index=False)
        except OSError as exc:
            raise ProcessingRequestError(
                "PROCESSING_STORAGE_FAILURE",
                "The cleaned data could not be saved.",
                status_code=500,
            ) from exc
        return stored_filename, f"exports/{stored_filename}"
    raise ProcessingRequestError(
        "PROCESSING_STORAGE_FAILURE",
        "The cleaned data could not be saved.",
        status_code=500,
    )
