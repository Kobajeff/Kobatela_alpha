from decimal import Decimal

import pytest

from app.services.invoice_ocr import enrich_metadata_with_invoice_ocr


class StubSettings:
    INVOICE_OCR_ENABLED = False
    INVOICE_OCR_PROVIDER = "none"


def _stub_settings(enabled: bool, provider: str):
    stub = StubSettings()
    stub.INVOICE_OCR_ENABLED = enabled
    stub.INVOICE_OCR_PROVIDER = provider
    return stub


def test_enrich_metadata_marks_disabled(monkeypatch):
    stub = _stub_settings(False, "none")
    monkeypatch.setattr("app.services.invoice_ocr.get_settings", lambda: stub)

    result = enrich_metadata_with_invoice_ocr(storage_url="s3://disabled", existing_metadata={})

    assert result["ocr_status"] == "disabled"
    assert result["ocr_provider"] == "none"


def test_enrich_metadata_records_provider_and_status(monkeypatch):
    stub = _stub_settings(True, "stub-provider")
    monkeypatch.setattr("app.services.invoice_ocr.get_settings", lambda: stub)
    monkeypatch.setattr(
        "app.services.invoice_ocr._call_external_ocr_provider",
        lambda storage_url: {"total_amount": "123.45", "iban": "DE89370400440532013000"},
    )

    result = enrich_metadata_with_invoice_ocr(storage_url="s3://invoice", existing_metadata={})

    assert result["ocr_status"] == "success"
    assert result["ocr_provider"] == "stub-provider"
    assert result["invoice_total_amount"] == Decimal("123.45")
    assert result["invoice_total_raw"] == "123.45"
    assert result["iban_last4"] == "3000"
    assert result["invoice_iban_last4"] == "3000"


def test_enrich_metadata_never_overwrites_existing_fields(monkeypatch):
    stub = _stub_settings(True, "stub-provider")
    monkeypatch.setattr("app.services.invoice_ocr.get_settings", lambda: stub)
    monkeypatch.setattr(
        "app.services.invoice_ocr._call_external_ocr_provider",
        lambda storage_url: {"total_amount": "123.45", "supplier_name": "ACME"},
    )

    existing = {"invoice_total_amount": Decimal("999.00"), "supplier_name": "User"}
    result = enrich_metadata_with_invoice_ocr(storage_url="s3://invoice", existing_metadata=existing)

    assert result["invoice_total_amount"] == Decimal("999.00")
    assert result["supplier_name"] == "User"
    # new fields are still populated when absent
    assert result["invoice_total_raw"] == "123.45"
    assert result["invoice_supplier_name"] == "ACME"


def test_enrich_metadata_normalizes_currency(monkeypatch):
    stub = _stub_settings(True, "stub-provider")
    monkeypatch.setattr("app.services.invoice_ocr.get_settings", lambda: stub)
    monkeypatch.setattr(
        "app.services.invoice_ocr._call_external_ocr_provider",
        lambda storage_url: {"currency": "eur"},
    )

    result = enrich_metadata_with_invoice_ocr(storage_url="s3://invoice", existing_metadata={})

    assert result["invoice_currency"] == "EUR"


def test_enrich_metadata_preserves_user_currency(monkeypatch):
    stub = _stub_settings(True, "stub-provider")
    monkeypatch.setattr("app.services.invoice_ocr.get_settings", lambda: stub)
    monkeypatch.setattr(
        "app.services.invoice_ocr._call_external_ocr_provider",
        lambda storage_url: {"currency": "eur"},
    )

    existing = {"invoice_currency": "USD"}
    result = enrich_metadata_with_invoice_ocr(storage_url="s3://invoice", existing_metadata=existing)

    assert result["invoice_currency"] == "USD"
