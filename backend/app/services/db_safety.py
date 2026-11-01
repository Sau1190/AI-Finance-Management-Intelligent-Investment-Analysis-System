"""All-or-nothing database write with artifact cleanup (Phase 14).

Beginner view:
  Some features write a file and then record it in the database. If the
  database step fails, the file must not be left behind, and the person must
  get a clear "database unavailable" answer - not a crash.

Technical view:
  Phases 4-10 each hand-wrote this try/commit/rollback/cleanup block.
  Phases 2 and 3 (processing, export) did not have it at all. This helper is
  the shared version used by those two; it deliberately imports nothing from
  SQLAlchemy so it can be tested with a fake session.
"""

import logging
from collections.abc import Callable

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

DATABASE_FAILURE_MESSAGE = "The result could not be saved because the database is unavailable. Nothing was kept."


def commit_or_cleanup(
    db,
    record,
    *,
    error_cls: type[AppError],
    cleanup: Callable[[], object] | None = None,
    message: str = DATABASE_FAILURE_MESSAGE,
):
    """add + commit + refresh `record`. On ANY failure: roll the session back,
    run `cleanup` (best effort - it must never mask the real problem), and raise
    `error_cls("DATABASE_FAILURE", message, 503)`. Only the exception TYPE is
    logged: a database driver's message can contain SQL text and parameters.
    """
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception as exc:  # noqa: BLE001 - every failure must roll back and clean up
        logger.error("Database write failed: %s", type(exc).__name__)
        try:
            db.rollback()
        except Exception as rollback_exc:  # noqa: BLE001
            logger.error("Rollback also failed: %s", type(rollback_exc).__name__)
        if cleanup is not None:
            try:
                cleanup()
            except Exception as cleanup_exc:  # noqa: BLE001
                logger.error("Cleanup after a failed database write also failed: %s", type(cleanup_exc).__name__)
        raise error_cls("DATABASE_FAILURE", message, status_code=503) from exc
    return record
