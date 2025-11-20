from decimal import Decimal

import pytest

from app.services import invoice_ocr
from app.services.invoice_ocr import normalize_invoice_amount_and_currency, normalize_invoice_metadata


def test_enrich_metadata_merges_and_preserves_user(monkeypatch):
    monkeypatch.setattr(
        invoice_ocr,
        "run_invoice_ocr_if_enabled",
        lambda _bytes: {
            "ocr_status": "success",
            "ocr_provider": "dummy",
            "total_amount": Decimal("123.45"),
            "currency": "EUR",
            "supplier_name": "ACME",
        },
    )

    existing = {"invoice_total_amount": Decimal("999.00"), "supplier_name": "User"}
    result = invoice_ocr.enrich_metadata_with_invoice_ocr(
        storage_url="s3://invoice", existing_metadata=existing, file_bytes=b"pdf"
    )

    assert result["invoice_total_amount"] == Decimal("999.00")
    assert result["supplier_name"] == "User"
    assert result["ocr_status"] == "success"
    assert result["ocr_provider"] == "dummy"
    assert result["ocr_raw"]["total_amount"] == Decimal("123.45")


def test_enrich_metadata_sets_invoice_fields_when_missing(monkeypatch):
    monkeypatch.setattr(
        invoice_ocr,
        "run_invoice_ocr_if_enabled",
        lambda _bytes: {
            "ocr_status": "success",
            "ocr_provider": "dummy",
            "total_amount": Decimal("321.00"),
            "currency": "usd",
            "iban_last4": "1234",
        },
    )

    result = invoice_ocr.enrich_metadata_with_invoice_ocr(
        storage_url="s3://invoice", existing_metadata={}, file_bytes=b"pdf"
    )

    assert result["invoice_total_amount"] == Decimal("321.00")
    assert result["invoice_currency"] == "usd"
    assert result["ocr_raw"]["iban_last4"] == "1234"
    invoice_ocr.InvoiceOCRResult.model_validate(result["ocr_raw"])


def test_normalize_invoice_amount_and_currency_happy_path():
    amount, currency, errors = normalize_invoice_amount_and_currency(
        {"invoice_total_amount": "1000.5", "invoice_currency": "usd"}
    )

    assert amount == Decimal("1000.50")
    assert currency == "USD"
    assert errors == []


def test_normalize_invoice_amount_and_currency_invalid_values():
    amount, currency, errors = normalize_invoice_amount_and_currency(
        {"invoice_total_amount": "abc", "invoice_currency": "US"}
    )

    assert amount is None
    assert currency is None
    assert "invalid_invoice_total_amount" in errors
    assert "invalid_invoice_currency" in errors


def test_normalize_invoice_metadata_surfaces_errors():
    normalized = normalize_invoice_metadata({"invoice_total_amount": "oops", "invoice_currency": "usd4"})

    assert normalized["invoice_total_amount"] is None
    assert normalized["invoice_currency"] is None
    assert "invalid_invoice_total_amount" in normalized.get("normalization_errors", [])
    assert "invalid_invoice_currency" in normalized.get("normalization_errors", [])

