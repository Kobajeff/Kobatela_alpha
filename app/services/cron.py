"""Background cron jobs for maintenance tasks."""
from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.usage_mandate import UsageMandate, UsageMandateStatus
from app.utils.time import utcnow


def expire_mandates_once() -> None:
    """Expire mandates whose validity period has elapsed."""

    db_factory = SessionLocal
    if db_factory is None:  # defensive, should not happen after init_engine()
        return

    db: Session = db_factory()
    try:
        now = utcnow()
        stmt = (
            update(UsageMandate)
            .where(
                UsageMandate.status == UsageMandateStatus.ACTIVE,
                UsageMandate.expires_at <= now,
            )
            .values(status=UsageMandateStatus.EXPIRED)
        )
        db.execute(stmt)
        db.commit()
    finally:
        db.close()
