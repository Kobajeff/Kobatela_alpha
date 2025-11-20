import pytest

from decimal import Decimal

from app.models import EscrowAgreement, EscrowStatus, Milestone, MilestoneStatus, Proof, User
from app.services.ai_proof_advisor import _sanitize_context
from app.utils.masking import AI_MASK_PLACEHOLDER, mask_metadata_for_ai
from app.utils.time import utcnow


def test_sanitize_context_masks_sensitive_fields():
    context = {
        "mandate_context": {"beneficiary_name": "Alice Beneficiary", "iban": "FR761234567890"},
        "backend_checks": {"iban_check": True, "amount_check": "ok"},
        "document_context": {
            "storage_url": "https://storage.example.com/proofs/invoice.pdf",
            "metadata": {
                "iban_full": "FR761234567890",
                "iban_last4": "7890",
                "email": "supplier@example.com",
                "invoice_total_amount": 123.45,
            },
        },
    }

    sanitized = _sanitize_context(context)

    masked_meta = sanitized["document_context"].get("metadata") or {}
    assert masked_meta["iban_full"] == AI_MASK_PLACEHOLDER
    assert masked_meta["email"] == AI_MASK_PLACEHOLDER
    assert "supplier_name" not in masked_meta
    assert masked_meta["iban_last4"] == AI_MASK_PLACEHOLDER
    assert masked_meta["invoice_total_amount"] == 123.45
    assert set(masked_meta["_ai_redacted_keys"]) == {"iban_full", "email", "iban_last4"}
    assert sanitized["mandate_context"]["beneficiary_name"] == "***masked***"
    assert sanitized["backend_checks"]["iban_check"] is True


def test_mask_metadata_for_ai_masks_sensitive_and_drops_unknown():
    masked = mask_metadata_for_ai(
        {
            "iban_full": "BE68539007547034",
            "email": "john@doe.com",
            "invoice_total_amount": 123.45,
            "invoice_currency": "eur",
            "client_secret": "super-secret",
            "beneficiary_address": "secret street",
        }
    )

    assert masked["iban_full"] == AI_MASK_PLACEHOLDER
    assert masked["email"] == AI_MASK_PLACEHOLDER
    assert masked["invoice_total_amount"] == 123.45
    assert masked["invoice_currency"] == "EUR"
    assert masked["beneficiary_address"] == AI_MASK_PLACEHOLDER
    assert masked["_ai_redacted_keys"] == [
        "iban_full",
        "email",
        "client_secret",
        "beneficiary_address",
    ]


def test_mask_metadata_for_ai_preserves_allowed_without_redaction_marker():
    masked = mask_metadata_for_ai(
        {
            "invoice_total_amount": 10,
            "invoice_currency": "usd",
        }
    )

    assert masked["invoice_total_amount"] == 10
    assert masked["invoice_currency"] == "USD"
    assert "_ai_redacted_keys" not in masked


def test_mask_metadata_for_ai_drops_unknown_keys():
    from app.utils.masking import mask_metadata_for_ai

    masked = mask_metadata_for_ai(
        {
            "iban_full": "BE68539007547034",
            "email": "john@doe.com",
            "invoice_total_amount": 123.45,
            "invoice_currency": "eur",
            "client_secret": "super-secret",
        }
    )

    assert masked["iban_full"] == "***redacted***"
    assert masked["email"] == "***redacted***"
    assert masked["invoice_total_amount"] == 123.45
    assert masked["invoice_currency"] == "EUR"
    assert masked["_ai_redacted_keys"] == ["iban_full", "email", "client_secret"]


@pytest.mark.anyio("asyncio")
async def test_proof_response_masks_sensitive_metadata(client, auth_headers, db_session):
    client_user = User(username="proof-client", email="proof-client@example.com")
    provider_user = User(username="proof-provider", email="proof-provider@example.com")
    db_session.add_all([client_user, provider_user])
    db_session.flush()

    escrow = EscrowAgreement(
        client_id=client_user.id,
        provider_id=provider_user.id,
        amount_total=Decimal("200.00"),
        currency="USD",
        status=EscrowStatus.FUNDED,
        release_conditions_json={"proof": "invoice"},
        deadline_at=utcnow(),
    )
    db_session.add(escrow)
    db_session.flush()

    milestone = Milestone(
        escrow_id=escrow.id,
        idx=1,
        label="Invoice",
        amount=Decimal("200.00"),
        proof_type="PDF",
        validator="SENDER",
        status=MilestoneStatus.WAITING,
    )
    db_session.add(milestone)
    db_session.commit()

    metadata = {
        "iban_full": "FR761234567890",
        "supplier_name": "Sensitive Supplier",
        "iban_last4": "7890",
    }
    response = await client.post(
        "/proofs",
        json={
            "escrow_id": escrow.id,
            "milestone_idx": 1,
            "type": "PDF",
            "storage_url": "https://storage.example.com/proof.pdf",
            "sha256": "proof-hash-privacy",
            "metadata": metadata,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["metadata"]["iban_full"].endswith("7890")
    assert payload["metadata"]["iban_full"] != metadata["iban_full"]
    assert payload["metadata"]["supplier_name"] == "***masked***"

    proof = db_session.get(Proof, payload["id"])
    assert proof.metadata_["iban_full"] == metadata["iban_full"]
    assert proof.metadata_["supplier_name"] == metadata["supplier_name"]
