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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
