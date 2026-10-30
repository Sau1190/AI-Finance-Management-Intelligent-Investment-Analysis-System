from pydantic import BaseModel


class DatabaseStatus(BaseModel):
    connected: bool
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    phase: int
    environment: str
    disclaimer: str
    database: DatabaseStatus
