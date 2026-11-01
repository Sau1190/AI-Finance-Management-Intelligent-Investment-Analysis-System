"""FastAPI application entrypoint.

Beginner view:
  This file creates the web server. Other files add routes and services.
  We do not put financial calculations here.

Technical view:
  App with CORS, API router under /api, and table creation on startup.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import init_db
from app.core.error_handlers import register_error_handlers
from app.core.http_safety import RequestSizeLimitMiddleware, SecurityHeadersMiddleware

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        init_db()
    except Exception:
        # API still starts; /api/health and uploads report database status.
        pass
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    lifespan=lifespan,
    description=(
        "Explainable financial analysis and investment decision-support system. "
        "Deterministic code calculates numbers. AI (later) only explains verified results. "
        "This is not an automated trading system and does not promise returns."
    ),
)

# Phase 14 hardening. Middleware order (last added = outermost):
#   SecurityHeaders -> CORS -> RequestSizeLimit -> routes
# so every answer (including CORS preflights and size refusals) carries the
# hardening headers, and a refusal still gets CORS headers the browser can read.

# Multipart framing around an upload (boundaries, part headers) - generous but bounded.
MULTIPART_OVERHEAD_BYTES = 64 * 1024
# Every non-upload body (sentiment texts are the largest: 100 x 2000 characters).
MAX_JSON_BODY_BYTES = 2 * 1024 * 1024


def request_size_rule(scope) -> tuple[int, str, str] | None:
    """Per-request body limit, read from settings each time so the upload
    ceiling stays configurable (MAX_UPLOAD_BYTES) and testable."""
    if scope.get("method") == "POST" and scope.get("path", "").rstrip("/") == "/api/files":
        limit = get_settings().max_upload_bytes + MULTIPART_OVERHEAD_BYTES
        return limit, "FILE_TOO_LARGE", "The upload is larger than the maximum allowed size."
    return MAX_JSON_BODY_BYTES, "REQUEST_TOO_LARGE", "The request body is too large."


app.add_middleware(RequestSizeLimitMiddleware, limit_for=request_size_rule)

# The API uses no cookies or sessions, so credentialed CORS is switched off, and
# only the methods/headers the dashboard really uses are allowed. A wildcard
# origin in CORS_ORIGINS is ignored (explicit origins only).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in settings.cors_origin_list if origin != "*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)
app.add_middleware(SecurityHeadersMiddleware)

register_error_handlers(app)

app.include_router(api_router, prefix="/api")


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, _exc: RequestValidationError) -> JSONResponse:
    """Keep our error envelope consistent even for framework-level request
    errors (e.g. a multipart upload with no filename never reaches our own
    validators). Never leak Pydantic internals or type names to the client.
    """
    return JSONResponse(
        status_code=422,
        content={"detail": {"code": "INVALID_REQUEST", "message": "The request could not be processed."}},
    )


@app.get("/")
def root() -> dict:
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "health": "/api/health",
        "files": "/api/files",
        "phase": settings.current_phase,
    }
