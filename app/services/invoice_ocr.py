"""Invoice OCR enrichment helpers."""
from __future__ import annotations

import logging
import time
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


def normalize_invoice_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize invoice amount/currency and surface errors explicitly.

    This helper is preserved for backward-compatibility with callers that
    expect the historical structure including a ``normalization_errors``
    array. New code should prefer ``normalize_invoice_amount_and_currency``
    which returns a tuple for clearer handling of errors.
    """

    amount, currency, errors = normalize_invoice_amount_and_currency(raw)
    out: dict[str, Any] = {}

    if amount is not None or "invalid_invoice_total_amount" in errors:
        out["invoice_total_amount"] = amount
    if currency is not None or "invalid_invoice_currency" in errors:
        out["invoice_currency"] = currency
    if errors:
        out["normalization_errors"] = errors

    return out


def normalize_invoice_amount_and_currency(
    metadata: Dict[str, Any],
) -> Tuple[Optional[Decimal], Optional[str], list[str]]:
    """Normalize invoice amount and currency without raising.

    Returns ``(amount, currency, errors)`` where errors is a list of
    normalization error codes. Amounts are parsed as ``Decimal`` with two
    decimals and currencies must be 3-letter alphabetic codes.
    """

    errors: list[str] = []

    raw_amount = metadata.get("invoice_total_amount") or metadata.get("total") or metadata.get("total_amount")
    amount: Decimal | None = None
    if raw_amount is not None:
        try:
            amount = Decimal(str(raw_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, TypeError, ValueError):
            amount = None
            errors.append("invalid_invoice_total_amount")

    raw_currency = str(metadata.get("invoice_currency") or metadata.get("currency") or "").strip()
    currency: str | None = None
    if raw_currency:
        if len(raw_currency) == 3 and raw_currency.isalpha():
            currency = raw_currency.upper()
        else:
            errors.append("invalid_invoice_currency")

    return amount, currency, errors


def enrich_metadata_with_invoice_ocr(
    *,
    storage_url: str,
    existing_metadata: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Enrich metadata with OCR info without overwriting user-supplied values."""

    start = time.monotonic()
    status = "success"
    provider = None
    metadata = dict(existing_metadata or {})
    provider = getattr(_current_settings(), "INVOICE_OCR_PROVIDER", "none")

    if not invoice_ocr_enabled():
        status = "skipped"
        logger.info("Invoice OCR disabled; skipping enrichment for %s", storage_url)
        metadata["ocr_status"] = "disabled"
        metadata["ocr_provider"] = provider
        return metadata

    try:
        raw = _call_external_ocr_provider(storage_url)
        normalized = _normalize_invoice_ocr(raw)

        if "invoice_total_amount" in normalized:
            if "invoice_total_amount" not in metadata:
                metadata["invoice_total_amount"] = normalized["invoice_total_amount"]
            else:
                metadata.setdefault("ocr", {})["invoice_total_amount"] = normalized["invoice_total_amount"]

        if "invoice_currency" in normalized:
            if "invoice_currency" not in metadata:
                metadata["invoice_currency"] = normalized["invoice_currency"]
            else:
                metadata.setdefault("ocr", {})["invoice_currency"] = normalized["invoice_currency"]

        for key, value in normalized.items():
            if key in {"invoice_total_amount", "invoice_currency"}:
                continue
            if key not in metadata:
                metadata[key] = value

        metadata["ocr_status"] = "success"
        metadata["ocr_provider"] = provider
        return metadata

    except Exception as exc:  # noqa: BLE001
        status = "error"
        logger.exception("Invoice OCR failed for %s: %s", storage_url, exc)
        metadata["ocr_status"] = "error"
        metadata["ocr_provider"] = provider
        return metadata
    finally:
        duration = time.monotonic() - start
        logger.info(
            "Invoice OCR enrichment completed",
            extra={
                "status": status,
                "duration_seconds": duration,
                "provider": provider,
                "storage_url": storage_url,
            },
        )
