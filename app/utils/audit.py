"""Audit logging helper utilities."""
from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.utils.time import utcnow


SENSITIVE_KEYS = {
    "iban",
    "iban_full",
    "iban_full_masked",
    "account_number",
    "card_number",
    "email",
    "storage_url",
    "psp_reference",
    "iban_last4",
}


def _mask_value(key: str, value: Any) -> Any:
    if value is None:
        return None

    if key in {"iban", "iban_full", "iban_full_masked", "account_number", "card_number"}:
        stripped = str(value).replace(" ", "")
        if len(stripped) <= 4:
            return f"***{stripped}"
        return f"***{stripped[-4:]}"

    if key == "iban_last4":
        return f"***{str(value)[-2:]}"

    if key == "email":
        text = str(value)
        if "@" in text:
            _, domain = text.split("@", 1)
            return f"***@{domain}"
        return "***"

    if key == "storage_url":
        text = str(value)
        base = text.split("?", 1)[0]
        if "/" in base:
            prefix = base.rsplit("/", 1)[0]
            return f"{prefix}/***"
        return "***/***"

    if key == "psp_reference":
        text = str(value)
        if len(text) <= 6:
            return "***"
        return f"***{text[-4:]}"

    return value


def sanitize_payload_for_audit(data: Any) -> Any:
    """Return a copy of ``data`` with obvious PII fields masked."""

    if isinstance(data, Mapping):
        sanitized: dict[str, Any] = {}
        for key, value in data.items():
            masked_value = _mask_value(key, value) if key in SENSITIVE_KEYS else value
            sanitized[key] = sanitize_payload_for_audit(masked_value)
        return sanitized

    if isinstance(data, list):
        return [sanitize_payload_for_audit(item) for item in data]

    return data


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
            data_json=sanitize_payload_for_audit(data or {}),
            at=utcnow(),
        )
    )


def actor_from_api_key(api_key: Any, fallback: str = "system") -> str:
    """Return the canonical actor string for a given API key object."""

    prefix = getattr(api_key, "prefix", None)
    if prefix:
        return f"apikey:{prefix}"
    return fallback
