from decimal import Decimal

import pytest

from decimal import Decimal

from app.models import EscrowAgreement, EscrowStatus, Milestone, MilestoneStatus, Proof, User
from app.services.ai_proof_advisor import _sanitize_context
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
                "supplier_name": "Very Sensitive Supplier",
                "email": "supplier@example.com",
            },
        },
    }

    sanitized = _sanitize_context(context)

    masked_meta = sanitized["document_context"].get("metadata") or {}
    assert masked_meta["iban_full"] == "***redacted***"
    assert masked_meta["email"] == "***redacted***"
    assert masked_meta["supplier_name"] == "Very Sensitive Supplier"
    assert sanitized["mandate_context"]["beneficiary_name"] == "***masked***"
    assert sanitized["backend_checks"]["iban_check"] is True


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
