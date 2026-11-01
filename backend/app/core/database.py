"""SQLAlchemy engine and session factory.

Beginner view:
  This is the door to the database. Routes should not open raw connections.
  Tests may use SQLite; the default app still targets PostgreSQL.

Technical view:
  SQLAlchemy 2.x engine. `configure_database()` lets tests point at a temp DB.
  Queries must stay parameterized. Never fabricate a successful connection.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""


engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def _connect_args(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {"connect_timeout": 3}


def configure_database(database_url: str | None = None) -> Engine:
    """Create (or recreate) the engine and session factory."""
    global engine, SessionLocal
    url = database_url or get_settings().database_url
    engine = create_engine(
        url,
        pool_pre_ping=True,
        future=True,
        connect_args=_connect_args(url),
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine


configure_database()


def get_engine() -> Engine:
    if engine is None:
        return configure_database()
    return engine


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        configure_database()
    assert SessionLocal is not None
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables if the database is reachable. Import models first."""
    from app.models import export_result as _export_result  # noqa: F401
    from app.models import fundamental_analysis_result as _fundamental_analysis_result  # noqa: F401
    from app.models import market_data_snapshot as _market_data_snapshot  # noqa: F401
    from app.models import technical_analysis_result as _technical_analysis_result  # noqa: F401
    from app.models import pdf_extraction_result as _pdf_extraction_result  # noqa: F401
    from app.models import processing_result as _processing_result  # noqa: F401
    from app.models import risk_analysis_result as _risk_analysis_result  # noqa: F401
    from app.models import score_result as _score_result  # noqa: F401
    from app.models import sentiment_result as _sentiment_result  # noqa: F401
    from app.models import uploaded_file as _uploaded_file  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def check_database_connection() -> dict:
    """Return a small status dict. Never fabricates a successful connection."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"connected": True, "error": None}
    except Exception as exc:  # noqa: BLE001 — health must not crash the API
        return {"connected": False, "error": type(exc).__name__}
