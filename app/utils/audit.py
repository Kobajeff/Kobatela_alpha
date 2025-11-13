"""Audit logging helper utilities."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.utils.time import utcnow


def log_audit(
    db: Session,
    *,
    actor: str,
    action: str,
    entity: str,
    entity_id: int | None,
    data: dict | None = None,
) -> None:
    """Persist an audit entry in the shared AuditLog table."""

    db.add(
        AuditLog(
            actor=actor,
            action=action,
            entity=entity,
            entity_id=entity_id if entity_id is not None else 0,
            data_json=data or {},
            at=utcnow(),
        )
    )
