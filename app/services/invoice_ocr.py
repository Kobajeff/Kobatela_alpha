"""Invoice OCR enrichment helpers."""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.config import get_settings

logger = logging.getLogger(__name__)


def _current_settings():
    return get_settings()


def invoice_ocr_enabled() -> bool:
    """Return True if the invoice OCR feature is enabled."""

    return bool(getattr(_current_settings(), "INVOICE_OCR_ENABLED", False))


def _call_external_ocr_provider(storage_url: str) -> Dict[str, Any]:
    """Call the configured OCR provider and return raw data.

    This is a stub for now; future phases will plug a real provider (Mindee, Tabscanner...).
    """

    provider = getattr(_current_settings(), "INVOICE_OCR_PROVIDER", "none")

    if provider == "none":
        return {}

    # Example placeholder for future integrations.
    logger.warning("Invoice OCR provider '%s' not implemented, returning empty result.", provider)
    return {}


def _normalize_invoice_ocr(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize raw OCR output into canonical invoice metadata keys."""

    if not raw:
        return {}

    total = raw.get("total_amount") or raw.get("amount") or None
    currency = raw.get("currency") or None
    date_value = raw.get("invoice_date") or raw.get("date") or None
    invoice_number = raw.get("invoice_number") or None
    supplier_name = raw.get("supplier_name") or raw.get("merchant_name") or None
    supplier_country = raw.get("supplier_country") or raw.get("country") or None
    supplier_city = raw.get("supplier_city") or raw.get("city") or None
    iban = raw.get("iban") or raw.get("bank_account") or None

    iban_last4 = iban[-4:] if isinstance(iban, str) and len(iban) >= 4 else None
    iban_full_masked = None
    if isinstance(iban, str) and len(iban) >= 8:
        masked_body = ''.join('*' if ch != ' ' else ' ' for ch in iban[:-4])
        iban_full_masked = f"{masked_body}{iban[-4:]}"

    normalized: Dict[str, Any] = {}

    if total is not None:
        try:
            normalized["invoice_total_amount"] = float(total)
        except (TypeError, ValueError):
            pass

    if currency:
        normalized["invoice_currency"] = str(currency).upper()

    if date_value:
        normalized["invoice_date"] = str(date_value)

    if invoice_number:
        normalized["invoice_number"] = str(invoice_number)

    if supplier_name:
        normalized["supplier_name"] = str(supplier_name)

    if supplier_country:
        normalized["supplier_country"] = str(supplier_country)

    if supplier_city:
        normalized["supplier_city"] = str(supplier_city)

    if iban_last4:
        normalized["iban_last4"] = iban_last4
    if iban_full_masked:
        normalized["iban_full_masked"] = iban_full_masked

    return normalized


def enrich_metadata_with_invoice_ocr(
    *,
    storage_url: str,
    existing_metadata: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Enrich metadata with OCR info without overwriting user-supplied values."""

    metadata = dict(existing_metadata or {})
    provider = getattr(_current_settings(), "INVOICE_OCR_PROVIDER", "none")

    if not invoice_ocr_enabled():
        metadata.setdefault("ocr_status", "disabled")
        metadata.setdefault("ocr_provider", provider)
        return metadata

    try:
        raw = _call_external_ocr_provider(storage_url)
        normalized = _normalize_invoice_ocr(raw)

        status = "ok" if normalized else "empty"

        for key, value in normalized.items():
            if key not in metadata or metadata.get(key) in (None, ""):
                metadata[key] = value

        metadata["ocr_status"] = status
        metadata["ocr_provider"] = provider
        return metadata

    except Exception as exc:  # noqa: BLE001
        logger.exception("Invoice OCR failed for %s: %s", storage_url, exc)
        metadata.setdefault("ocr_status", "error")
        metadata.setdefault("ocr_provider", provider)
        return metadata
