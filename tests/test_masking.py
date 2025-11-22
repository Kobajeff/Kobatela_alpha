"""Tests for metadata masking helpers."""
from app.utils.masking import mask_metadata_for_ai


def test_mask_metadata_for_ai_drops_unknown_fields():
    metadata = {
        "invoice_total_amount": 100,
        "invoice_currency": "eur",
        "iban_full": "BE12345678901234",
        "supplier_tax_id": "SENSITIVE",
    }

    safe = mask_metadata_for_ai(metadata)

    assert safe["invoice_total_amount"] == 100
    assert safe["invoice_currency"] == "EUR"
    assert safe["iban_full"] == "***redacted***"
    assert "supplier_tax_id" not in safe
