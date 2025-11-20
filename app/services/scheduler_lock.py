"""Simple DB-backed lock to ensure only one scheduler runs."""
from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import db
from app.models.scheduler_lock import SchedulerLock


LOCK_NAME = "default"
LOCK_TTL_SECONDS = 300


def _session(db_session: Session | None = None) -> tuple[Session | None, bool]:
    if db_session is not None:
        return db_session, False
    session_factory = db.SessionLocal
    if session_factory is None:
        session_factory = db.get_sessionmaker()
    if session_factory is None:
        return None, False
    return session_factory(), True


def _owner_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


def try_acquire_scheduler_lock(
    name: str = LOCK_NAME,
    *,
    ttl_seconds: int = LOCK_TTL_SECONDS,
    db_session: Session | None = None,
) -> bool:
    """Attempt to acquire the scheduler lock with owner + TTL safety."""

    session, should_close = _session(db_session)
    if session is None:
        return False

    owner = _owner_id()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=ttl_seconds)

    try:
        with session.begin():
            lock = (
                session.execute(
                    select(SchedulerLock).where(SchedulerLock.name == name).with_for_update()
                ).scalar_one_or_none()
            )

            if lock is None:
                session.add(
                    SchedulerLock(
                        name=name,
                        owner=owner,
                        acquired_at=now,
                        expires_at=expires,
                    )
                )
                return True

            expires_at = lock.expires_at
            if expires_at is not None and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            if expires_at is None or expires_at <= now:
                lock.owner = owner
                lock.acquired_at = now
                lock.expires_at = expires
                return True

            if lock.owner == owner:
                lock.expires_at = expires
                return True

            return False
    except IntegrityError:
        session.rollback()
        return False
    finally:
        if should_close:
            session.close()


def refresh_scheduler_lock(
    name: str = LOCK_NAME, *, ttl_seconds: int = LOCK_TTL_SECONDS, db_session: Session | None = None
) -> None:
    """Refresh the TTL of the scheduler lock when owned by this runner."""

    session, should_close = _session(db_session)
    if session is None:
        return

    owner = _owner_id()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=ttl_seconds)

    try:
        with session.begin():
            lock = (
                session.execute(
                    select(SchedulerLock).where(SchedulerLock.name == name).with_for_update()
                ).scalar_one_or_none()
            )
            if lock and lock.owner == owner:
                lock.expires_at = expires
    finally:
        if should_close:
            session.close()


def release_scheduler_lock(name: str = LOCK_NAME, *, db_session: Session | None = None) -> None:
    """Release the scheduler lock if held by this runner."""

    session, should_close = _session(db_session)
    if session is None:
        return

    owner = _owner_id()
    try:
        with session.begin():
            lock = (
                session.execute(
                    select(SchedulerLock).where(SchedulerLock.name == name).with_for_update()
                ).scalar_one_or_none()
            )
            if lock and lock.owner == owner:
                session.delete(lock)
    finally:
        if should_close:
            session.close()


def describe_scheduler_lock(name: str = LOCK_NAME) -> dict[str, object]:
    """Return a lightweight description of the current scheduler lock state."""

    session, should_close = _session()
    if session is None:
        return {"status": "unknown", "owner": None}

    owner = _owner_id()
    try:
        lock = (
            session.execute(select(SchedulerLock).where(SchedulerLock.name == name)).scalar_one_or_none()
        )
        if lock is None:
            return {"status": "none", "owner": None}
        if lock.owner == owner:
            return {"status": "owned_by_self", "owner": lock.owner}
        return {"status": "owned_by_other", "owner": lock.owner}
    finally:
        if should_close:
            session.close()
