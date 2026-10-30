"""Store original uploads under unique names. Never overwrite a source file."""

from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.core.exceptions import FileIntakeError


def upload_directory() -> Path:
    path = Path(get_settings().upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def unique_stored_filename(file_type: str) -> str:
    return f"{uuid4().hex}.{file_type}"


def save_original_bytes(content: bytes, file_type: str) -> tuple[str, str]:
    """Write bytes once. If the generated name exists, pick another. Never overwrite."""
    directory = upload_directory()
    try:
        for _ in range(5):
            stored_filename = unique_stored_filename(file_type)
            destination = directory / stored_filename
            if destination.exists():
                continue
            destination.write_bytes(content)
            storage_key = f"uploads/{stored_filename}"
            return stored_filename, storage_key
    except OSError as exc:
        raise FileIntakeError(
            "STORAGE_FAILURE",
            "The file could not be stored.",
            status_code=500,
        ) from exc
    raise FileIntakeError("STORAGE_FAILURE", "The file could not be stored.", status_code=500)


def delete_stored_file(stored_filename: str) -> None:
    path = upload_directory() / stored_filename
    if path.is_file():
        path.unlink()
