"""The API's error envelope, standard library only (Phase 14).

Every failure answer is `{"detail": {"code": ..., "message": ...}}`. This is
the single definition of that shape and of the generic messages; the FastAPI
handlers in error_handlers.py only wire it up.
"""

from http import HTTPStatus

DATABASE_FAILURE_MESSAGE = (
    "The database is unavailable or the change could not be saved. Nothing was kept; try again later."
)
INTERNAL_ERROR_MESSAGE = "The server hit an unexpected problem. Try again; if it keeps happening, check the server log."


def error_body(code: str, message: str) -> dict:
    return {"detail": {"code": code, "message": message}}


def is_envelope(detail) -> bool:
    return isinstance(detail, dict) and "code" in detail and "message" in detail


def code_for_status(status_code: int) -> str:
    """Stable code for a bare HTTP status (404 -> HTTP_404). Deliberately NOT
    "NOT_FOUND": the dashboard treats a 404 whose code contains NOT_FOUND as
    "nothing stored yet" (an empty state), and an unknown URL must stay an
    error rather than look like an empty result.
    """
    return f"HTTP_{status_code}"


def message_for_status(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "The request could not be completed."


def envelope_for_http_error(status_code: int, detail) -> dict:
    """Pass our own envelope through untouched; wrap a bare string detail."""
    if is_envelope(detail):
        return {"detail": detail}
    return error_body(code_for_status(status_code), message_for_status(status_code))
