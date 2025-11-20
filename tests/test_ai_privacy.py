import pytest
from app.services.ai_proof_advisor import _sanitize_context
from app.utils.masking import AI_MASK_PLACEHOLDER


def test_ai_masks_sensitive_in_mandate():
    ctx = {
        "mandate_context": {
            "beneficiary_iban": "BE12345678901234",
            "email": "test@example.com",
        },
        "document_context": {"metadata": {}},
        "backend_checks": {},
    }

    cleaned = _sanitize_context(ctx)

    assert cleaned["mandate_context"]["beneficiary_iban"] == AI_MASK_PLACEHOLDER
    assert cleaned["mandate_context"]["email"] == AI_MASK_PLACEHOLDER


def test_ai_masks_sensitive_in_backend():
    ctx = {
        "backend_checks": {
            "phone_number": "+32470000000",
            "address": "Rue de Test 42",
        },
        "document_context": {"metadata": {}},
        "mandate_context": {},
    }

    cleaned = _sanitize_context(ctx)

    assert cleaned["backend_checks"]["phone_number"] == AI_MASK_PLACEHOLDER
    assert cleaned["backend_checks"]["address"] == AI_MASK_PLACEHOLDER


def test_ai_allows_valid_invoice_metadata():
    ctx = {
        "document_context": {
            "metadata": {
                "invoice_total_amount": 100,
                "invoice_currency": "EUR",
            }
        },
        "backend_checks": {},
        "mandate_context": {},
    }

    cleaned = _sanitize_context(ctx)

    meta = cleaned["document_context"]["metadata"]
    assert meta["invoice_total_amount"] == 100
    assert meta["invoice_currency"] == "EUR"


def test_ai_redacts_unknown_keys():
    ctx = {
        "document_context": {
            "metadata": {
                "custom_field": "SECRET",
                "invoice_total_amount": 100,
            }
        },
        "mandate_context": {},
        "backend_checks": {},
    }

    cleaned = _sanitize_context(ctx)
    meta = cleaned["document_context"]["metadata"]

    assert "custom_field" not in meta
    assert "_ai_redacted_keys" in meta
    assert "custom_field" in meta["_ai_redacted_keys"]
