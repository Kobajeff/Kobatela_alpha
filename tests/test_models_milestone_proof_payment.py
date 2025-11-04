"""Tests for milestone, proof, and payment models."""
from datetime import UTC, datetime

from app.models import (
    EscrowAgreement,
    EscrowStatus,
    Milestone,
    Payment,
    PaymentStatus,
    Proof,
    User,
)


def test_create_milestone_proof_payment(db_session):
    client = User(username="client", email="client@example.com", is_active=True)
    provider = User(username="provider", email="provider@example.com", is_active=True)
    db_session.add_all([client, provider])
    db_session.flush()

    escrow = EscrowAgreement(
        client_id=client.id,
        provider_id=provider.id,
        amount_total=1000.0,
        currency="USD",
        status=EscrowStatus.DRAFT,
        release_conditions_json={"type": "milestone"},
        deadline_at=datetime.now(tz=UTC),
    )
    db_session.add(escrow)
    db_session.flush()

    milestone = Milestone(
        escrow_id=escrow.id,
        idx=1,
        label="Initial milestone",
        amount=500.0,
        proof_type="SIGNED_CONTRACT",
        validator="SENDER",
    )
    db_session.add(milestone)
    db_session.flush()

    proof = Proof(
        escrow_id=escrow.id,
        milestone_id=milestone.id,
        type="SIGNED_CONTRACT",
        storage_url="https://example.com/proof.pdf",
        sha256="abc123",
        metadata_={"pages": 3},
        status="PENDING",
        created_at=datetime.now(tz=UTC),
    )
    db_session.add(proof)

    payment = Payment(
        escrow_id=escrow.id,
        milestone_id=milestone.id,
        amount=500.0,
        psp_ref="PSP123",
        status=PaymentStatus.INITIATED,
        idempotency_key="pay-1",
    )
    db_session.add(payment)

    db_session.commit()

    assert milestone.id is not None
    assert proof.id is not None
    assert payment.id is not None
