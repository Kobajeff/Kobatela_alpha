"""Audit logging helper utilities."""
from __future__ import annotations

from typing import Any

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


def actor_from_api_key(api_key: Any, fallback: str = "system") -> str:
    """Return the canonical actor string for a given API key object."""

    prefix = getattr(api_key, "prefix", None)
    if prefix:
        return f"apikey:{prefix}"
    return fallback
