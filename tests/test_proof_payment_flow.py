"""End-to-end test for proof approval and payment execution."""
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import EscrowAgreement, EscrowStatus, Milestone, MilestoneStatus, Payment, PaymentStatus


@pytest.mark.anyio("asyncio")
async def test_proof_approval_triggers_payment(client, auth_headers, db_session):
    client_resp = await client.post(
        "/users",
        json={"username": "escrow-client", "email": "escrow-client@example.com"},
        headers=auth_headers,
    )
    provider_resp = await client.post(
        "/users",
        json={"username": "escrow-provider", "email": "escrow-provider@example.com"},
        headers=auth_headers,
    )
    assert client_resp.status_code == 201
    assert provider_resp.status_code == 201
    client_id = client_resp.json()["id"]
    provider_id = provider_resp.json()["id"]

    escrow_resp = await client.post(
        "/escrows",
        json={
            "client_id": client_id,
            "provider_id": provider_id,
            "amount_total": 500.0,
            "currency": "USD",
            "release_conditions": {"type": "milestone"},
            "deadline_at": datetime.now(tz=UTC).isoformat(),
        },
        headers=auth_headers,
    )
    assert escrow_resp.status_code == 201
    escrow_id = escrow_resp.json()["id"]

    milestone = Milestone(
        escrow_id=escrow_id,
        idx=1,
        label="Prototype delivery",
        amount=500.0,
        proof_type="PHOTO",
        validator="SENDER",
    )
    db_session.add(milestone)
    db_session.flush()

    deposit_headers = {**auth_headers, "Idempotency-Key": "proof-flow-deposit"}
    deposit_resp = await client.post(
        f"/escrows/{escrow_id}/deposit",
        json={"amount": 500.0},
        headers=deposit_headers,
    )
    assert deposit_resp.status_code == 200

    proof_resp = await client.post(
        "/proofs",
        json={
            "escrow_id": escrow_id,
            "milestone_idx": 1,
            "type": "PHOTO",
            "storage_url": "https://example.com/proof.jpg",
            "sha256": "abc123",
        },
        headers=auth_headers,
    )
    assert proof_resp.status_code == 201
    proof_id = proof_resp.json()["id"]

    db_session.refresh(milestone)
    assert milestone.status == MilestoneStatus.PENDING_REVIEW

    decision_resp = await client.post(
        f"/proofs/{proof_id}/decision",
        json={"decision": "approved", "note": "Looks good"},
        headers=auth_headers,
    )
    assert decision_resp.status_code == 200
    assert decision_resp.json()["status"] == "APPROVED"

    db_session.refresh(milestone)
    assert milestone.status == MilestoneStatus.PAID

    payment = db_session.scalars(select(Payment).where(Payment.milestone_id == milestone.id)).one()
    assert payment.status == PaymentStatus.SENT

    escrow = db_session.get(EscrowAgreement, escrow_id)
    assert escrow is not None
    db_session.refresh(escrow)
    assert escrow.status == EscrowStatus.RELEASED

    second_exec = await client.post(f"/payments/execute/{payment.id}", headers=auth_headers)
    assert second_exec.status_code == 200
    assert second_exec.json()["status"] == "SENT"
