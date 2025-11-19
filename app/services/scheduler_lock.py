"""Simple DB-backed lock to ensure only one scheduler runs."""
from __future__ import annotations

from datetime import UTC, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import db
from app.models.scheduler_lock import SchedulerLock
from app.utils.time import utcnow


LOCK_NAME = "default"
LOCK_TTL = timedelta(minutes=10)


def _session(db_session: Session | None = None) -> tuple[Session | None, bool]:
    if db_session is not None:
        return db_session, False
    session_factory = db.SessionLocal
    if session_factory is None:
        session_factory = db.get_sessionmaker()
    if session_factory is None:
        return None, False
    return session_factory(), True


def try_acquire_scheduler_lock(name: str = LOCK_NAME, *, db_session: Session | None = None) -> bool:
    """Attempt to acquire the scheduler lock with TTL-based eviction."""

    session, should_close = _session(db_session)
    if session is None:
        return False

    try:
        now = utcnow()
        existing = session.execute(select(SchedulerLock).where(SchedulerLock.name == name)).scalar_one_or_none()
        if existing:
            acquired_at = existing.acquired_at
            if acquired_at.tzinfo is None:
                acquired_at = acquired_at.replace(tzinfo=UTC)
            else:
                acquired_at = acquired_at.astimezone(UTC)
            if (now - acquired_at) > LOCK_TTL:
                session.delete(existing)
                session.commit()
            else:
                return False

        session.add(SchedulerLock(name=name, acquired_at=now))
        session.commit()
        return True
    except IntegrityError:
        session.rollback()
        return False
    finally:
        if should_close:
            session.close()


def release_scheduler_lock(name: str = LOCK_NAME, *, db_session: Session | None = None) -> None:
    """Release the scheduler lock if held by this runner."""

    session, should_close = _session(db_session)
    if session is None:
        return

    try:
        existing = session.execute(select(SchedulerLock).where(SchedulerLock.name == name)).scalar_one_or_none()
        if existing:
            session.delete(existing)
            session.commit()
    finally:
        if should_close:
            session.close()
