"""Helpers for masking sensitive metadata before exposing it externally."""
from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

MASKED_PLACEHOLDER = "***masked***"
logger = logging.getLogger(__name__)

# Keys that should always be fully masked regardless of value length
FULL_MASK_KEYS = {
    "beneficiary_name",
    "beneficiary_address",
    "supplier_name",
    "supplier_address",
    "supplier_city",
    "supplier_country",
    "account_holder",
}

# Keys containing account or IBAN data
ACCOUNT_KEYS = {
    "iban",
    "iban_full",
    "iban_full_masked",
    "iban_masked",
    "iban_last4",
    "beneficiary_iban",
    "beneficiary_iban_last4",
    "supplier_iban",
    "supplier_iban_last4",
    "account_number",
}

CONTACT_KEYS = {"email", "phone", "mobile", "contact_phone"}


def _clean_account_value(value: Any) -> str:
    text = "" if value is None else str(value)
    normalized = "".join(ch for ch in text if ch.isalnum())
    if not normalized:
        return "***"
    if len(normalized) <= 4:
        return f"***{normalized}"
    return "*" * (len(normalized) - 4) + normalized[-4:]


def _mask_email(value: Any) -> str:
    text = "" if value is None else str(value)
    if "@" not in text:
        return "***@***"
    local, domain = text.split("@", 1)
    safe_domain = domain or "***"
    return f"***@{safe_domain}"


def _mask_phone(value: Any) -> str:
    text = "" if value is None else str(value)
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return "***"
    tail = digits[-2:] if len(digits) >= 2 else digits
    return f"***{tail}"


def _mask_leaf(key: str, value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value

    lower = key.lower()
    if lower in FULL_MASK_KEYS:
        return MASKED_PLACEHOLDER

    if lower in CONTACT_KEYS or lower.endswith("_email"):
        return _mask_email(value)

    if "phone" in lower or "mobile" in lower:
        return _mask_phone(value)

    if ("iban" in lower and "check" not in lower and "match" not in lower) or lower in ACCOUNT_KEYS:
        return _clean_account_value(value)

    if "account_number" in lower:
        return _clean_account_value(value)

    return value


def _mask_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, Mapping):
            masked[key] = _mask_mapping(value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            masked[key] = [
                _mask_mapping(item) if isinstance(item, Mapping) else _mask_leaf(key, item)
                for item in value
            ]
        else:
            masked[key] = _mask_leaf(key, value)
    return masked


def mask_proof_metadata(metadata: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """Return a sanitized copy of the proof metadata without leaking PII."""

    if metadata is None:
        return None
    if not isinstance(metadata, Mapping):
        return metadata
    return _mask_mapping(metadata)


AI_MASK_PLACEHOLDER = "***redacted***"

# Allowlist stricte de ce qui peut être envoyé à OpenAI
AI_ALLOWED_METADATA_KEYS = {
    "invoice_total_amount",
    "invoice_currency",
    "invoice_number",
    "invoice_date",
    "supplier_country",
    "supplier_city",
    "beneficiary_city",
    "beneficiary_country",
    "gps_lat",
    "gps_lng",
    "gps_accuracy_m",
    "file_type",
    "file_mime_type",
    "file_pages",
    "status",
    "ocr_status",
    "ocr_provider",
}

# Patterns sensibles (IBAN, mail, phone, address, identifiers…)
SENSITIVE_PATTERNS = (
    "iban",
    "account",
    "email",
    "phone",
    "tel",
    "addr",
    "ssn",
    "nif",
    "id_",
    "ident",
    "passport",
)


def mask_metadata_for_ai(metadata):
    """
    Apply strict privacy rules before sending metadata to OpenAI.

    - Allowed keys → pass through unchanged.
    - Sensitive keys → replaced by placeholder (***redacted***).
    - Unknown keys → removed from context but tracked in _ai_redacted_keys.
    """
    if not isinstance(metadata, dict):
        return {}

    cleaned = {}
    redacted_keys = []

    for key, value in metadata.items():
        key_lower = key.lower()

        # 1) Sensitive → mask
        if any(pattern in key_lower for pattern in SENSITIVE_PATTERNS):
            cleaned[key] = AI_MASK_PLACEHOLDER
            redacted_keys.append(key)
            continue

        # 2) Allowed → keep
        if key_lower in AI_ALLOWED_METADATA_KEYS:
            if key_lower == "invoice_currency" and isinstance(value, str):
                cleaned[key] = value.upper()
            else:
                cleaned[key] = value
            continue

        # 3) Unknown key → drop + log in special field
        redacted_keys.append(key)

    if redacted_keys:
        cleaned["_ai_redacted_keys"] = redacted_keys

    return cleaned


__all__ = ["mask_proof_metadata", "mask_metadata_for_ai"]
