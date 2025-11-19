from app.services.scheduler_lock import release_scheduler_lock, try_acquire_scheduler_lock


def test_scheduler_lock_enforces_single_owner(db_session):
    # Ensure clean slate
    release_scheduler_lock()

    assert try_acquire_scheduler_lock() is True
    assert try_acquire_scheduler_lock() is False

    release_scheduler_lock()
