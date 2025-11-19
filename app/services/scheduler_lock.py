"""Simple DB-backed lock to ensure only one scheduler runs."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import db
from app.utils.time import utcnow


LOCK_NAME = "default"


def try_acquire_scheduler_lock(name: str = LOCK_NAME) -> bool:
    """Attempt to acquire the scheduler lock.

    Returns True if the lock was acquired, False if another runner already owns it.
    """

    session_factory = db.SessionLocal
    if session_factory is None:
        return False

    session = session_factory()
    try:
        session.execute(
            text("INSERT INTO scheduler_locks (name, acquired_at) VALUES (:name, :at)"),
            {"name": name, "at": utcnow()},
        )
        session.commit()
        return True
    except IntegrityError:
        session.rollback()
        return False
    finally:
        session.close()


def release_scheduler_lock(name: str = LOCK_NAME) -> None:
    """Release the scheduler lock if held by this runner."""

    session_factory = db.SessionLocal
    if session_factory is None:
        return

    session = session_factory()
    try:
        session.execute(text("DELETE FROM scheduler_locks WHERE name = :name"), {"name": name})
        session.commit()
    finally:
        session.close()
