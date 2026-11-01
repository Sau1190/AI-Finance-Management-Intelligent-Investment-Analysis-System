"""Bounded upload reading (Phase 14). Standard library + project exceptions only.

`await upload.read()` loads the whole body into memory before any size check.
This reads at most `limit + 1` bytes and refuses as soon as the limit is
passed, so an oversized upload can never be fully materialised by our code.
"""

from app.core.exceptions import FileIntakeError

CHUNK_BYTES = 64 * 1024


async def read_upload_limited(upload, limit: int) -> bytes:
    """Read an UploadFile-like object (async `read(n)`) up to `limit` bytes.
    Raises FileIntakeError FILE_TOO_LARGE (400, the same code/status the
    validator uses) the moment more than `limit` bytes are seen."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise FileIntakeError(
                "FILE_TOO_LARGE",
                f"The file exceeds the maximum size of {limit} bytes.",
            )
        chunks.append(chunk)
    return b"".join(chunks)
