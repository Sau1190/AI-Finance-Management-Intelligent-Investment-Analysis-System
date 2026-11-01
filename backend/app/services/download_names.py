"""File-name helpers for generated downloads (Phase 14). Standard library only."""

import unicodedata

MAX_DB_FILENAME = 255  # length of the original_filename column
EXPORT_SUFFIX = "-export.xlsx"


def build_export_filename(original_filename: str) -> str:
    """`<original>-export.xlsx`, shortened so the whole name always fits the
    255-character database column (an uploaded name may already be 255 long;
    PostgreSQL rejects an oversized value, SQLite silently allows it)."""
    stem = (original_filename or "").strip() or "export"
    return stem[: MAX_DB_FILENAME - len(EXPORT_SUFFIX)] + EXPORT_SUFFIX


def safe_download_filename(name: str | None, fallback: str = "export.xlsx") -> str:
    """A name safe to put in a Content-Disposition header: no quotes,
    semicolons, path separators or control characters; never empty."""
    cleaned = "".join(
        ch for ch in (name or "")
        if ch not in {'"', ";", "/", "\\", "\r", "\n", "\x00"} and unicodedata.category(ch)[0] != "C"
    ).strip().strip(".")
    return cleaned[:MAX_DB_FILENAME] or fallback
