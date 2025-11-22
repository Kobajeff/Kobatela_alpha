"""Invoice OCR enrichment helpers."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Mapping, Optional, Protocol

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_OCR_CALLS_TOTAL = 0
_OCR_ERRORS_TOTAL = 0


class InvoiceOCRResult(BaseModel):
    """
    Normalized OCR result for an invoice-like document.

    This is the internal contract for what the OCR layer is allowed to return.
    All providers MUST conform to this schema.
    """

    ocr_status: str = Field(..., description="Overall OCR status, e.g. 'disabled', 'success', 'error'")
    ocr_provider: Optional[str] = Field(default=None, description="Provider identifier, e.g. 'dummy', 'openai'")
    total_amount: Optional[Decimal] = Field(default=None, description="Total amount detected on invoice")
    currency: Optional[str] = Field(default=None, description="3-letter currency code, if detected", min_length=3, max_length=3)
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    iban_last4: Optional[str] = None
    supplier_name: Optional[str] = None

    @field_validator("total_amount")
    @classmethod
    def _validate_amount(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        if value is None:
            return value

        try:
            decimal_value = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Invalid total_amount") from exc
        return decimal_value

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("Currency must be a 3-letter code")
        return normalized

    @field_validator("iban_last4")
    @classmethod
    def _validate_iban_last4(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        trimmed = value.strip()
        if len(trimmed) != 4:
            raise ValueError("IBAN last 4 must be exactly 4 characters")
        return trimmed


class OCRProvider(Protocol):
    """Protocol for OCR providers."""

    def extract(self, file_bytes: bytes) -> Dict[str, Any]:
        """
        Perform OCR on the given document bytes and return a raw dict.

        The raw dict will be validated and normalized via InvoiceOCRResult.
        Implementations may return extra keys; only allowed/known keys
        will be preserved by the Pydantic model.
        """
        ...


@dataclass
class DummyOCRProvider:
    """No-op provider used when OCR is disabled or not configured."""

    name: str = "dummy"

    def extract(self, file_bytes: bytes) -> Dict[str, Any]:
        # Minimal contract: always returns an object that can be validated.
        return {
            "ocr_status": "disabled",
            "ocr_provider": self.name,
            "total_amount": None,
            "currency": None,
        }


_OCR_PROVIDERS: Dict[str, OCRProvider] = {
    "dummy": DummyOCRProvider(),
    # Future: "openai": OpenAIOCRProvider(...),
    # Future: "tesseract": TesseractOCRProvider(...),
}


def _record_ocr_success() -> None:
    global _OCR_CALLS_TOTAL
    _OCR_CALLS_TOTAL += 1


def _record_ocr_error() -> None:
    global _OCR_CALLS_TOTAL, _OCR_ERRORS_TOTAL
    _OCR_CALLS_TOTAL += 1
    _OCR_ERRORS_TOTAL += 1


def get_ocr_stats() -> Dict[str, int]:
    return {
        "calls": _OCR_CALLS_TOTAL,
        "errors": _OCR_ERRORS_TOTAL,
    }


def invoice_ocr_enabled() -> bool:
    """Return True if the invoice OCR feature is enabled."""

    return bool(getattr(get_settings(), "INVOICE_OCR_ENABLED", False))


def get_ocr_provider() -> OCRProvider:
    """
    Pick the OCR provider based on settings.
    For now, returns 'dummy' if OCR is disabled or no provider configured.
    """

    settings = get_settings()
    provider_name = getattr(settings, "INVOICE_OCR_PROVIDER", "dummy")

    provider = _OCR_PROVIDERS.get(provider_name)
    if not provider:
        logger.warning(
            "Unknown OCR provider configured; falling back to dummy",
            extra={"provider": provider_name},
        )
        provider = _OCR_PROVIDERS["dummy"]
    return provider


def normalize_ocr_result(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Validate and normalize a raw OCR output into a canonical dict
    based on InvoiceOCRResult.

    - Uses Pydantic for validation/coercion.
    - On validation error, returns a safe 'error' structure.
    """

    try:
        model = InvoiceOCRResult.model_validate(raw)
        return model.model_dump()
    except ValidationError as exc:
        logger.warning(
            "Invoice OCR result failed validation; returning error structure",
            extra={"errors": exc.errors()},
        )
        return {
            "ocr_status": "error",
            "ocr_provider": raw.get("ocr_provider") or "unknown",
            "total_amount": None,
            "currency": None,
            "invoice_number": None,
            "invoice_date": None,
            "iban_last4": None,
            "supplier_name": None,
        }


def run_invoice_ocr_if_enabled(file_bytes: bytes) -> Dict[str, Any]:
    """
    High-level OCR entry point used by proofs.submit_proof.

    - If OCR is disabled in settings, returns a canonical 'disabled' result.
    - If enabled, delegates to the configured provider and normalizes the result.
    """

    settings = get_settings()
    if not getattr(settings, "INVOICE_OCR_ENABLED", False):
        _record_ocr_success()
        return InvoiceOCRResult(
            ocr_status="disabled",
            ocr_provider="disabled",
            total_amount=None,
            currency=None,
        ).model_dump()

    provider = get_ocr_provider()
    try:
        raw = provider.extract(file_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Invoice OCR provider call failed", extra={"provider": getattr(provider, "name", None)}
        )
        _record_ocr_error()
        return InvoiceOCRResult(
            ocr_status="error",
            ocr_provider=getattr(provider, "name", "unknown"),
            total_amount=None,
            currency=None,
        ).model_dump()

    normalized = normalize_ocr_result(raw)
    if normalized.get("ocr_status") == "error":
        _record_ocr_error()
    else:
        _record_ocr_success()
    return normalized


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
) -> tuple[Optional[Decimal], Optional[str], list[str]]:
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
    file_bytes: bytes | None = None,
) -> Dict[str, Any]:
    """Enrich metadata with OCR info without overwriting user-supplied values."""

    metadata = dict(existing_metadata or {})
    ocr_result = run_invoice_ocr_if_enabled(file_bytes or b"")

    metadata.setdefault("ocr_status", ocr_result.get("ocr_status"))
    metadata.setdefault("ocr_provider", ocr_result.get("ocr_provider"))

    if "total_amount" in ocr_result and metadata.get("invoice_total_amount") is None:
        metadata["invoice_total_amount"] = ocr_result.get("total_amount")
    if "currency" in ocr_result and metadata.get("invoice_currency") is None:
        metadata["invoice_currency"] = ocr_result.get("currency")

    metadata.setdefault("ocr_raw", {})
    metadata["ocr_raw"].update(ocr_result)

    logger.info(
        "Invoice OCR enrichment completed",
        extra={
            "storage_url": storage_url,
            "ocr_status": ocr_result.get("ocr_status"),
            "ocr_provider": ocr_result.get("ocr_provider"),
        },
    )

    return metadata

