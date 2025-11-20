"""Invoice OCR enrichment helpers."""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Optional, Tuple

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

    normalized: Dict[str, Any] = {}

    total_raw = raw.get("total_amount") or raw.get("amount")
    normalized["invoice_total_raw"] = total_raw

    total_dec: Decimal | None = None
    if total_raw is not None:
        try:
            total_dec = Decimal(str(total_raw)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, TypeError, ValueError):
            total_dec = None

    if total_dec is not None:
        normalized["invoice_total_amount"] = total_dec

    currency = raw.get("currency") or raw.get("invoice_currency")
    if currency:
        normalized["invoice_currency"] = str(currency).upper()

    date_value = raw.get("invoice_date") or raw.get("date")
    if date_value:
        normalized["invoice_date"] = str(date_value)

    invoice_number = raw.get("invoice_number")
    if invoice_number:
        normalized["invoice_number"] = str(invoice_number)

    supplier_name = raw.get("supplier_name") or raw.get("merchant_name")
    if supplier_name:
        normalized["invoice_supplier_name"] = str(supplier_name)
        normalized.setdefault("supplier_name", str(supplier_name))

    supplier_country = raw.get("supplier_country") or raw.get("country")
    if supplier_country:
        normalized["invoice_supplier_country"] = str(supplier_country)
        normalized.setdefault("supplier_country", str(supplier_country))

    supplier_city = raw.get("supplier_city") or raw.get("city")
    if supplier_city:
        normalized["invoice_supplier_city"] = str(supplier_city)
        normalized.setdefault("supplier_city", str(supplier_city))

    iban = raw.get("iban") or raw.get("bank_account")
    if isinstance(iban, str):
        iban_clean = iban.replace(" ", "")
        if iban_clean:
            last4 = iban_clean[-4:]
            normalized["invoice_iban_last4"] = last4
            normalized.setdefault("iban_last4", last4)
            if len(iban_clean) >= 4:
                masked = f"****{last4}"
                normalized["invoice_iban_masked"] = masked
                normalized.setdefault("iban_full_masked", masked)

    return {k: v for k, v in normalized.items() if v is not None}


def normalize_invoice_amount_and_currency(
    metadata: Dict[str, Any],
) -> Tuple[Optional[Decimal], Optional[str]]:
    """Extract and normalize invoice total amount & currency from metadata.

    - Accepts strings or numbers for amount.
    - Normalizes to Decimal with 2 decimal places.
    - Currency must be a 3-letter uppercase code, otherwise None.
    """

    raw_amount = metadata.get("invoice_total_amount") or metadata.get("total_amount")
    raw_currency = metadata.get("invoice_currency") or metadata.get("currency")

    amount_dec: Optional[Decimal] = None
    if raw_amount is not None:
        try:
            amount_dec = Decimal(str(raw_amount)).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError):
            amount_dec = None

    currency_norm: Optional[str] = None
    if isinstance(raw_currency, str):
        code = raw_currency.strip().upper()
        if len(code) == 3 and code.isalpha():
            currency_norm = code

    return amount_dec, currency_norm


def enrich_metadata_with_invoice_ocr(
    *,
    storage_url: str,
    existing_metadata: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Enrich metadata with OCR info without overwriting user-supplied values."""

    metadata = dict(existing_metadata or {})
    provider = getattr(_current_settings(), "INVOICE_OCR_PROVIDER", "none")

    if not invoice_ocr_enabled():
        logger.info("Invoice OCR disabled; skipping enrichment for %s", storage_url)
        metadata["ocr_status"] = "disabled"
        metadata["ocr_provider"] = provider
        return metadata

    try:
        raw = _call_external_ocr_provider(storage_url)
        normalized = _normalize_invoice_ocr(raw)

        for key, value in normalized.items():
            if key not in metadata:
                metadata[key] = value

        metadata["ocr_status"] = "success"
        metadata["ocr_provider"] = provider
        return metadata

    except Exception as exc:  # noqa: BLE001
        logger.exception("Invoice OCR failed for %s: %s", storage_url, exc)
        metadata["ocr_status"] = "error"
        metadata["ocr_provider"] = provider
        return metadata
