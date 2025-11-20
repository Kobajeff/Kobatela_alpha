from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.scheduler_lock import SchedulerLock
from app.services.scheduler_lock import (
    release_scheduler_lock,
    try_acquire_scheduler_lock,
)


def test_scheduler_lock_enforces_single_owner(db_session):
    # Ensure clean slate
    release_scheduler_lock(db_session=db_session)

    assert try_acquire_scheduler_lock(db_session=db_session) is True
    assert try_acquire_scheduler_lock(db_session=db_session) is True

    release_scheduler_lock(db_session=db_session)


def test_lock_cannot_be_taken_if_not_expired(monkeypatch, db_session):
    release_scheduler_lock(db_session=db_session)

    monkeypatch.setattr("app.services.scheduler_lock._owner_id", lambda: "node-A")
    assert try_acquire_scheduler_lock(db_session=db_session, ttl_seconds=300)

    monkeypatch.setattr("app.services.scheduler_lock._owner_id", lambda: "node-B")
    assert try_acquire_scheduler_lock(db_session=db_session, ttl_seconds=300) is False

    release_scheduler_lock(db_session=db_session)


def test_lock_can_be_reacquired_after_expiry(monkeypatch, db_session):
    release_scheduler_lock(db_session=db_session)

    monkeypatch.setattr("app.services.scheduler_lock._owner_id", lambda: "node-A")
    assert try_acquire_scheduler_lock(db_session=db_session, ttl_seconds=60)

    # Manually expire the lock
    with db_session.begin():
        lock = db_session.execute(select(SchedulerLock).where(SchedulerLock.name == "default")).scalar_one()
        lock.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    monkeypatch.setattr("app.services.scheduler_lock._owner_id", lambda: "node-B")
    assert try_acquire_scheduler_lock(db_session=db_session, ttl_seconds=300)

    release_scheduler_lock(db_session=db_session)


def test_describe_scheduler_lock_contains_expiry(db_session, monkeypatch):
    from app.services.scheduler_lock import describe_scheduler_lock

    release_scheduler_lock(db_session=db_session)
    monkeypatch.setattr("app.services.scheduler_lock._owner_id", lambda: "node-A")
    assert try_acquire_scheduler_lock(db_session=db_session, ttl_seconds=60)

    info = describe_scheduler_lock(db_session=db_session)
    assert info.get("present") is True
    assert "age_seconds" in info
    assert "expires_in_seconds" in info

    release_scheduler_lock(db_session=db_session)
