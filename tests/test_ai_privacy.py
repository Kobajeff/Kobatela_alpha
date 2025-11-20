import pytest
from app.services.ai_proof_advisor import _sanitize_context
from app.utils.masking import AI_MASK_PLACEHOLDER, mask_metadata_for_ai


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


def test_ai_preserves_backend_and_mandate_signals():
    ctx = {
        "backend_checks": {
            "distance": 12.5,
            "date_diff_days": 3,
            "duplicate_hash": "abc123",
        },
        "mandate_context": {
            "mandate_amount": 2500,
            "mandate_currency": "EUR",
        },
        "document_context": {"metadata": {}},
    }

    cleaned = _sanitize_context(ctx)

    assert cleaned["backend_checks"]["distance"] == 12.5
    assert cleaned["backend_checks"]["date_diff_days"] == 3
    assert cleaned["backend_checks"]["duplicate_hash"] == "abc123"
    assert cleaned["mandate_context"]["mandate_amount"] == 2500
    assert cleaned["mandate_context"]["mandate_currency"] == "EUR"


def test_ai_drops_unexpected_mandate_and_backend_fields():
    ctx = {
        "backend_checks": {
            "distance": 42,
            "raw_storage_url": "https://secret-storage",
            "geofence_configured": True,
        },
        "mandate_context": {
            "mandate_amount": 99,
            "escrow_id": "escrow-1234",
            "milestone_label": "Very sensitive label",
        },
        "document_context": {"metadata": {}},
    }

    cleaned = _sanitize_context(ctx)

    assert "raw_storage_url" not in cleaned["backend_checks"]
    assert "escrow_id" not in cleaned["mandate_context"]
    assert "milestone_label" not in cleaned["mandate_context"]
def test_mask_metadata_for_ai_logs_redacted_keys():
    metadata = {
        "invoice_total_amount": 100,
        "iban_full": "BE68539007547034",
        "email": "john@doe.com",
        "custom_field": "should_not_be_sent",
    }

    cleaned = mask_metadata_for_ai(metadata)

    assert cleaned["invoice_total_amount"] == 100
    assert cleaned["iban_full"] == AI_MASK_PLACEHOLDER

    redacted = cleaned.get("_ai_redacted_keys") or []
    assert "iban_full" in redacted
    assert "email" in redacted
    assert "custom_field" in redacted
