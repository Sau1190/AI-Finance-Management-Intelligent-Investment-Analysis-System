# Excel Module Specification

## Purpose
Excel is a first-class part of the AI Finance Management project. It is used both as an input format and as a professional analysis/export format.

## Input capabilities
- Accept `.xlsx` files.
- Detect workbook sheets.
- Inspect headers and likely financial columns.
- Detect data types.
- Check missing values and duplicate rows.
- Preserve the original uploaded workbook as read-only source data.
- Normalize supported financial tables into an internal tabular representation.

## Processing pipeline
XLSX upload → file validation → workbook inspection → sheet/header detection → data-type checks → missing/duplicate checks → normalization → validation status → cleaned preview → analysis.

## Output workbook
Generate a separate analysis workbook; never overwrite the uploaded source.

Recommended sheets:
1. Raw Data
2. Cleaned Data
3. Financial Metrics
4. Market/Stock Metrics
5. Technical Indicators
6. Sentiment
7. Scores
8. What–How–Why Summary

## Formatting requirements
- Clear header formatting
- Appropriate number/date/percentage formats
- Sensible column widths
- Freeze panes
- Filters where useful
- Conditional formatting for meaningful warnings/scores
- Basic charts only when they improve interpretation

## Libraries
- Pandas: tabular processing and analysis
- OpenPyXL: workbook inspection/editing and formatting
- XlsxWriter: optional later if advanced workbook generation is justified

## Testing
Representative workbooks should cover:
- one-sheet clean data
- multiple sheets
- missing values
- duplicate rows
- unexpected columns
- mixed data types
- invalid dates/numbers
- empty sheets
- formulas/source workbooks
- large-but-valid workbooks

## Security
- Validate extension and MIME/content where practical.
- Enforce upload size limits.
- Use generated safe filenames.
- Store uploads outside executable/static paths.
- Never expose server filesystem paths to users.
- Do not execute spreadsheet macros.
- Never overwrite the original uploaded workbook.
