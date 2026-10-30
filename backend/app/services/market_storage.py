"""Generated market-data artifacts (one price-bar CSV per successful fetch).

Same guarantees as the other generated-artifact stores: dedicated directory,
generated non-colliding names, exclusive creation (never overwrites), a write
that fails part-way removes its own truncated file, and rollback deletion is
best-effort and confined to this directory.
"""

import csv
import io
import logging
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.core.exceptions import MarketDataRequestError

logger = logging.getLogger(__name__)

BAR_COLUMNS = ["date", "open", "high", "low", "close", "volume"]


def market_directory() -> Path:
    path = Path(get_settings().market_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def bars_to_csv(bars: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(BAR_COLUMNS)
    for bar in bars:
        writer.writerow([bar[column] for column in BAR_COLUMNS])
    return buffer.getvalue()


def save_bars_csv(csv_text: str) -> tuple[str, str]:
    """Write a bar CSV. Returns (stored_filename, storage_key)."""
    directory = market_directory()
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
            raise MarketDataRequestError(
                "MARKET_STORAGE_FAILURE", "The market data could not be saved.", status_code=500
            ) from exc
        return stored_filename, f"market/{stored_filename}"
    raise MarketDataRequestError(
        "MARKET_STORAGE_FAILURE", "Could not generate a unique filename for market data.", status_code=500
    )


def read_bars_csv(storage_key: str) -> list[dict] | None:
    """Read a stored bar CSV back into native-typed bars (file-name part of the
    key only). None if the file is missing or not a valid bar CSV.
    """
    path = market_directory() / Path(storage_key).name
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return [
            {
                "date": row["date"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
            }
            for row in rows
        ]
    except (OSError, KeyError, ValueError):
        return None


def delete_artifacts(storage_keys: list[str]) -> list[str]:
    """Best-effort rollback by storage key. Never raises; returns keys it could
    not remove. Only the file-name part of a key is used, so a key can never
    address anything outside the market directory.
    """
    directory = market_directory()
    not_removed: list[str] = []
    for key in storage_keys:
        try:
            (directory / Path(key).name).unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove market data artifact %s", Path(key).name)
            not_removed.append(key)
    return not_removed
