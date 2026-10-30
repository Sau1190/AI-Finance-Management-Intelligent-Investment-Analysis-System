"""Build a formatted, professional .xlsx export from Phase 2's already
computed output.

Deliberately narrow: this module only lays out and formats data it is
given. It never computes financial ratios, market data, technical
indicators, sentiment, risk, or scores — those require later, out-of-scope
phases and building them here would mean inventing numbers. What it does
format is real: the original raw grid, Phase 2's cleaned/normalized data,
and Phase 2's data-quality findings.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
import math

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

HEADER_FILL = PatternFill(start_color="FFD9E1F2", end_color="FFD9E1F2", fill_type="solid")
HEADER_FONT = Font(bold=True)
MISSING_FILL = PatternFill(start_color="FFFCE4E4", end_color="FFFCE4E4", fill_type="solid")
MAX_COLUMN_WIDTH = 40
MIN_COLUMN_WIDTH = 8

_NUMBER_FORMATS = {
    "integer": "#,##0",
    "float": "#,##0.00",
    "date": "yyyy-mm-dd",
}

_INVALID_SHEET_CHARS = set(r"[]:*?/\\")


@dataclass
class WorksheetExport:
    """Everything one processed worksheet contributes to the export. Built
    by export_service from Phase 2's ProcessingResult + a fresh read of the
    original file — this dataclass carries no logic of its own.
    """

    sheet_name: str
    row_count: int
    column_count: int
    missing_total: int
    duplicate_row_count: int
    inconsistent_total: int
    cleaned_data_status: str
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    raw_df: pd.DataFrame | None = None
    header_row_index: int | None = None
    cleaned_df: pd.DataFrame | None = None
    column_types: dict[str, str] = field(default_factory=dict)


def _safe_sheet_title(name: str, used: set[str]) -> str:
    """Excel sheet names: <=31 chars, no [ ] : * ? / \\, unique per workbook."""
    cleaned = "".join(ch for ch in name if ch not in _INVALID_SHEET_CHARS).strip() or "Sheet"
    base = cleaned[:31]
    candidate = base
    suffix = 1
    while candidate in used:
        suffix_str = f"~{suffix}"
        candidate = base[: 31 - len(suffix_str)] + suffix_str
        suffix += 1
    used.add(candidate)
    return candidate


def _autosize_columns(ws: Worksheet, frame_width: int, header_row: int, data_row_start: int, data_row_end: int) -> None:
    for col_idx in range(1, frame_width + 1):
        letter = get_column_letter(col_idx)
        longest = len(str(ws.cell(row=header_row, column=col_idx).value or ""))
        # Sample rather than scan every row on very large sheets — width is cosmetic.
        sample_end = min(data_row_end, data_row_start + 200)
        for row_idx in range(data_row_start, sample_end + 1):
            value = ws.cell(row=row_idx, column=col_idx).value
            if value is not None:
                longest = max(longest, len(str(value)))
        ws.column_dimensions[letter].width = max(MIN_COLUMN_WIDTH, min(MAX_COLUMN_WIDTH, longest + 2))


def _append_literal_row(ws: Worksheet, values: list) -> None:
    """Append values while keeping untrusted strings literal in Excel.

    openpyxl treats strings beginning with ``=`` as formulas by default.
    Uploaded cell values and headers must remain data when exported.
    """
    ws.append(values)
    for cell in ws[ws.max_row]:
        if isinstance(cell.value, str):
            cell.data_type = "s"


def _write_summary_sheet(wb: Workbook, worksheets: list[WorksheetExport], processing_failed_note: str | None) -> None:
    ws = wb.active
    ws.title = "Summary"

    if processing_failed_note:
        ws["A1"] = "Processing did not complete for this file"
        ws["A1"].font = Font(bold=True)
        ws["A2"] = processing_failed_note
        ws["A2"].data_type = "s"
        ws.column_dimensions["A"].width = 100
        return

    headers = [
        "Worksheet", "Rows", "Columns", "Missing Values",
        "Duplicate Rows", "Inconsistent Values", "Cleaned Data", "Warnings", "Errors",
    ]
    _append_literal_row(ws, headers)
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL

    for sheet in worksheets:
        _append_literal_row(ws, [
            sheet.sheet_name, sheet.row_count, sheet.column_count, sheet.missing_total,
            sheet.duplicate_row_count, sheet.inconsistent_total, sheet.cleaned_data_status,
            len(sheet.warnings), len(sheet.errors),
        ])

    last_row = ws.max_row
    ws.freeze_panes = "A2"
    if last_row >= 2:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{last_row}"
    _autosize_columns(ws, len(headers), header_row=1, data_row_start=2, data_row_end=last_row)

    if last_row >= 2 and any(s.row_count for s in worksheets):
        chart = BarChart()
        chart.title = "Rows per worksheet"
        chart.y_axis.title = "Rows"
        data = Reference(ws, min_col=2, min_row=1, max_row=last_row)
        categories = Reference(ws, min_col=1, min_row=2, max_row=last_row)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(categories)
        chart.height, chart.width = 8, 16
        ws.add_chart(chart, f"A{last_row + 3}")


def _write_raw_sheet(wb: Workbook, title: str, raw_df: pd.DataFrame, header_row_index: int | None) -> None:
    ws = wb.create_sheet(title)
    for row in raw_df.itertuples(index=False, name=None):
        _append_literal_row(ws, ["" if pd.isna(v) else v for v in row])

    if raw_df.empty:
        return

    header_excel_row = (header_row_index if header_row_index is not None else 0) + 1
    if header_excel_row <= ws.max_row:
        for cell in ws[header_excel_row]:
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
    ws.freeze_panes = f"A{header_excel_row + 1}"
    _autosize_columns(ws, raw_df.shape[1], header_row=header_excel_row, data_row_start=1, data_row_end=ws.max_row)


def _write_cleaned_sheet(wb: Workbook, title: str, cleaned_df: pd.DataFrame, column_types: dict[str, str]) -> None:
    ws = wb.create_sheet(title)
    columns = list(cleaned_df.columns)
    _append_literal_row(ws, columns)
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL

    for row in cleaned_df.itertuples(index=False, name=None):
        _append_literal_row(ws, ["" if pd.isna(v) else v for v in row])

    last_row = ws.max_row
    # Coerce cell values to real numeric/date types (lossless, deterministic
    # — the type was already established by Phase 2) so number formats and
    # Excel's own sort/filter behave correctly, not just look formatted.
    for col_idx, name in enumerate(columns, start=1):
        col_type = column_types.get(name)
        number_format = _NUMBER_FORMATS.get(col_type)
        if not number_format:
            continue
        for row_idx in range(2, last_row + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            if cell.value in (None, ""):
                continue
            coerced = _coerce_cell(cell.value, col_type)
            if coerced is not None:
                cell.value = coerced
                cell.number_format = number_format

    ws.freeze_panes = "A2"
    if last_row >= 1:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{last_row}"
    if last_row >= 2:
        data_range = f"A2:{get_column_letter(len(columns))}{last_row}"
        ws.conditional_formatting.add(
            data_range,
            FormulaRule(formula=["ISBLANK(A2)"], fill=MISSING_FILL),
        )
    _autosize_columns(ws, len(columns), header_row=1, data_row_start=2, data_row_end=last_row)


def _coerce_cell(value, col_type: str):
    """Best-effort, lossless type coercion for display only. Returns None
    (leave the cell as its original string) rather than guess when a value
    does not actually conform — a column being mostly numeric does not mean
    every cell is.
    """
    try:
        if col_type == "integer":
            parsed = Decimal(str(value).replace(",", ""))
            if not parsed.is_finite() or parsed != parsed.to_integral_value():
                return None
            return int(parsed)
        if col_type == "float":
            parsed = float(str(value).replace(",", ""))
            return parsed if math.isfinite(parsed) else None
        if col_type == "date":
            parsed = pd.to_datetime(str(value), errors="coerce", format="mixed")
            return None if pd.isna(parsed) else parsed.to_pydatetime()
    except (ValueError, TypeError, InvalidOperation):
        return None
    return None


def build_workbook(
    worksheets: list[WorksheetExport],
    *,
    processing_failed_note: str | None = None,
) -> bytes:
    """Assemble the full export workbook and return its bytes. Sheet order:
    Summary, then Raw/Cleaned pairs per worksheet in processing order.
    """
    wb = Workbook()
    _write_summary_sheet(wb, worksheets, processing_failed_note)

    used_titles = {"Summary"}
    single_sheet = len(worksheets) == 1
    sheet_titles = iter(_data_sheet_titles(worksheets, used_titles, single_sheet))
    for sheet in worksheets:
        if sheet.raw_df is not None:
            _write_raw_sheet(wb, next(sheet_titles), sheet.raw_df, sheet.header_row_index)
        if sheet.cleaned_df is not None:
            _write_cleaned_sheet(wb, next(sheet_titles), sheet.cleaned_df, sheet.column_types)

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def get_workbook_sheet_names(worksheets: list[WorksheetExport]) -> list[str]:
    """Return the exact sheet names that build_workbook will create."""
    used_titles = {"Summary"}
    return ["Summary", *_data_sheet_titles(worksheets, used_titles, len(worksheets) == 1)]


def _data_sheet_titles(
    worksheets: list[WorksheetExport], used_titles: set[str], single_sheet: bool
) -> list[str]:
    titles: list[str] = []
    for sheet in worksheets:
        raw_title_base = "Raw Data" if single_sheet else f"Raw - {sheet.sheet_name}"
        cleaned_title_base = "Cleaned Data" if single_sheet else f"Cleaned - {sheet.sheet_name}"
        if sheet.raw_df is not None:
            titles.append(_safe_sheet_title(raw_title_base, used_titles))
        if sheet.cleaned_df is not None:
            titles.append(_safe_sheet_title(cleaned_title_base, used_titles))
    return titles
