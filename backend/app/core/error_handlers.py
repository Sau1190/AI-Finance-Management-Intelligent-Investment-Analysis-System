"""One consistent, safe error envelope for the whole API (Phase 14).

Beginner view:
  Every failure answer looks the same - `{"detail": {"code": ..., "message":
  ...}}` - and never contains file paths, SQL, stack traces or secrets.

Technical view:
  Routes already translate expected problems (`AppError`) themselves. These
  handlers are the safety net for everything else:
    * a database error that a service re-raised   -> 503 DATABASE_FAILURE
    * any other `AppError` that reached the top   -> its own status/code
    * Starlette/FastAPI HTTP errors with a plain-string detail (unknown URL,
      wrong method...)                              -> the same envelope
    * any unexpected exception                      -> 500 INTERNAL_ERROR
  Only the exception TYPE is logged - exception text from pandas, openpyxl,
  httpx or the database driver can embed uploaded data, URLs or credentials.
  (Starlette still re-raises an unexpected exception after answering, so the
  server console keeps its traceback for the developer; the client never
  sees it.)
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.error_envelope import (
    DATABASE_FAILURE_MESSAGE,
    INTERNAL_ERROR_MESSAGE,
    envelope_for_http_error,
    error_body,
)
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope_for_http_error(exc.status_code, exc.detail),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.to_detail()})

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error("Database error reached the API boundary: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content=error_body("DATABASE_FAILURE", DATABASE_FAILURE_MESSAGE))

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled error reached the API boundary: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content=error_body("INTERNAL_ERROR", INTERNAL_ERROR_MESSAGE))
