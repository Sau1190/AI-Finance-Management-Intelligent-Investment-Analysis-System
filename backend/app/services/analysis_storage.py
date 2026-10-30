"""Generated analysis artifacts (per-worksheet metric CSVs).

Same guarantees as the other generated-artifact stores: files go to a
dedicated directory (never the originals' directory), get generated
non-colliding names, are created exclusively (never overwritten), a write
that fails part-way removes its own truncated file, and rollback deletion is
best-effort and confined to the analysis directory.
"""

import csv
import logging
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.core.exceptions import AnalysisRequestError

logger = logging.getLogger(__name__)


def analysis_directory() -> Path:
    path = Path(get_settings().analysis_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_metrics_csv(csv_text: str) -> tuple[str, str]:
    """Write one worksheet's metric CSV. Returns (stored_filename, storage_key)."""
    directory = analysis_directory()
    for _ in range(5):
        stored_filename = f"{uuid4().hex}.csv"
        destination = directory / stored_filename
        try:
            with destination.open("x", encoding="utf-8", newline="") as handle:
                handle.write(csv_text)
        except FileExistsError:
            continue
        except OSError as exc:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                logger.exception("Could not remove partially written artifact %s", stored_filename)
            raise AnalysisRequestError(
                "ANALYSIS_STORAGE_FAILURE", "The analysis metrics could not be saved.", status_code=500
            ) from exc
        return stored_filename, f"analysis/{stored_filename}"
    raise AnalysisRequestError(
        "ANALYSIS_STORAGE_FAILURE",
        "Could not generate a unique filename for an analysis artifact.",
        status_code=500,
    )


def read_csv_rows(storage_key: str) -> list[dict[str, str]] | None:
    """Read a stored analysis CSV as raw string rows (file-name part of the key
    only, so a key cannot point outside the analysis directory). None if the
    file is missing or unreadable.
    """
    path = analysis_directory() / Path(storage_key).name
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, csv.Error, UnicodeDecodeError):
        return None


def delete_artifacts(storage_keys: list[str]) -> list[str]:
    """Best-effort rollback by storage key. Never raises; returns keys it
    could not remove. Only the file-name part of a key is used, so a key can
    never address anything outside the analysis directory.
    """
    directory = analysis_directory()
    not_removed: list[str] = []
    for key in storage_keys:
        try:
            (directory / Path(key).name).unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove analysis artifact %s", Path(key).name)
            not_removed.append(key)
    return not_removed
