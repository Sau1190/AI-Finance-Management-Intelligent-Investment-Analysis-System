# PDF module (Phase 4 — verified complete; storage-failure handling updated 2026-10-10)

Deterministic extraction of literal text and tables from uploaded PDFs.
No OCR, no LLM, no financial interpretation — later phases decide what the
extracted content means.

## Pipeline

1. Upload (Phase 1: extension, size, `%PDF` signature, safe storage)
2. `POST /api/files/{file_id}/extract` locates the stored original (read-only)
3. PyMuPDF opens the bytes
   - password-protected → `FAILED` ("password-protected"); no password is ever guessed
   - unparseable → `FAILED` (generic message; details logged server-side only)
   - more than `max_pdf_pages` pages → `FAILED` with `PDF_TOO_LARGE`; nothing is partially extracted
4. Per page: literal text (`page.get_text()`) and tables (`page.find_tables()`)
5. Full text (one `.txt` per page with text) and each table (one `.csv`) are
   written to `backend/storage/extracts/` under generated names — never overwritten
6. A `PdfExtractionResult` row stores metadata, storage keys, and bounded previews

## Completeness and storage failures (all-or-nothing)

Saved text and table files are **required** artifacts: a result is `COMPLETE`
only if every artifact it describes was saved. If saving any page's text or any
table fails — or page extraction fails unexpectedly — the whole run is
`FAILED`:

- `error_message` names `EXTRACTION_STORAGE_FAILURE` (or the failing page for an
  unexpected error); `page_count` is still reported; `pages` is empty, so no
  page can describe a file that does not exist.
- Every artifact already written during that run is deleted (rollback). The
  deleter is best-effort: it never raises, logs anything it cannot remove, and
  can only address files inside the extracts directory.
- A write that fails part-way (e.g. disk full) removes its own truncated file
  before the error is raised. Files are created exclusively, so an existing
  file is never overwritten.
- If the result row itself cannot be saved to the database, the artifacts
  written for it are deleted and the error propagates.
- The failed run is still an inspectable `FAILED` result (HTTP 201), and the
  error text contains no filesystem paths or low-level error details.

Not covered by this rule: table *detection* is best-effort. If detection raises
on a page, that page gets a warning and keeps its text; no table artifact was
promised for it.

## Result shape

`PdfExtractionResultResponse`: `id`, `file_id`, `status` (`COMPLETE` | `FAILED`),
`created_at`, `error_message`, `page_count`, `pages[]`.

Each page: `page_number` (1-based), `char_count`, `text_preview` (first 500
chars), `text_storage_key` (null when the page has no text), `table_count`,
`tables[]` (`table_index`, `row_count`, `column_count`, `preview_rows` — first
5 rows, `storage_key` to the full CSV), `warnings[]`.

A page with no extractable text is **COMPLETE with a warning** that OCR is not
performed — it is not an error and writes no empty file.

## API

- `POST /api/files/{file_id}/extract` — 201 with the result (a `FAILED` run is still 201); 400 `UNSUPPORTED_FILE_TYPE` for non-PDFs; 404 `FILE_NOT_FOUND`
- `GET /api/files/{file_id}/extract` — latest result; 404 `EXTRACTION_RESULT_NOT_FOUND` if never extracted

## Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| `EXTRACTS_DIR` | `backend/storage/extracts` | Generated text/table artifacts (separate from originals and exports) |
| `MAX_PDF_PAGES` | 200 | Page-count ceiling per PDF |

## Guarantees

- The original PDF is only ever read; tests assert it is byte-identical after extraction.
- Errors use the project's `{code, message}` envelope; no stack traces or filesystem paths reach clients.
- Table detection is best-effort: a failure adds a page warning and never blocks that page's text.
- Saving extracted text/tables is not best-effort: a failure to save fails the whole run and rolls back its artifacts (see above).

## Known limitations

- Scanned/image-only pages produce no text (no OCR).
- Borderless or irregular tables may be missed or split; table cells are literal text, with no header detection or typing.
- Not yet connected to Phase 2 normalization; mapping PDF tables to financial concepts is future work.

## Tests

`backend/tests/test_extraction.py` (22 tests): single/multi-page text, table
detection, bounded table preview, blank page warning, encrypted PDF, corrupt
PDF, over-limit PDF, wrong file type, original-file integrity, missing file,
GET before extraction, GET returns latest — plus storage-failure regressions:
text-save failure, failure on a later page (earlier artifacts rolled back),
table-save failure (same-page text rolled back), partial/truncated write
removed, unexpected page failure, best-effort deleter behaviour and directory
confinement, database failure after artifacts were written, and a check that a
successful run leaves exactly the files its result describes.
