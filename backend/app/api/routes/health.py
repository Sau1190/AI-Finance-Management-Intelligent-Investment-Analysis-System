"""Health-check endpoint.

Beginner view:
  This is a simple "is the server alive?" URL. We also report whether
  PostgreSQL is reachable. A missing database does not invent fake data;
  it reports disconnected.

Technical view:
  GET /api/health is used by tests, the frontend, and later monitoring.
"""

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.database import check_database_connection
from app.schemas.health import DatabaseStatus, HealthResponse

router = APIRouter(tags=["health"])

DISCLAIMER = (
    "This system is an educational investment decision-support tool. "
    "It does not promise investment returns and is not automated trading advice."
)


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    settings = get_settings()
    db = check_database_connection()
    overall = "ok" if db["connected"] else "degraded"
    return HealthResponse(
        status=overall,
        service=settings.app_name,
        phase=settings.current_phase,
        environment=settings.app_env,
        disclaimer=DISCLAIMER,
        database=DatabaseStatus(connected=db["connected"], error=db["error"]),
    )
