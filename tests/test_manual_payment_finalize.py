"""Manual payment execution should finalize escrow state."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import (
    EscrowAgreement,
    EscrowDeposit,
    EscrowEvent,
    EscrowStatus,
    Milestone,
    MilestoneStatus,
    Payment,
    PaymentStatus,
    User,
)


@pytest.mark.anyio
async def test_manual_payment_finalizes_escrow(client, admin_headers, db_session):
    now = datetime.now(tz=UTC)
    client_user = User(username=f"client-{uuid4().hex[:8]}", email=f"client-{uuid4().hex[:8]}@example.com")
    provider_user = User(username=f"provider-{uuid4().hex[:8]}", email=f"provider-{uuid4().hex[:8]}@example.com")
    db_session.add_all([client_user, provider_user])
    db_session.flush()

    escrow = EscrowAgreement(
        client_id=client_user.id,
        provider_id=provider_user.id,
        amount_total=Decimal("100.00"),
        currency="USD",
        status=EscrowStatus.RELEASABLE,
        release_conditions_json={"type": "milestones"},
        deadline_at=now + timedelta(days=7),
    )
    db_session.add(escrow)
    db_session.flush()

    deposit = EscrowDeposit(escrow_id=escrow.id, amount=Decimal("150.00"), idempotency_key=f"dep-{uuid4().hex[:6]}")
    milestone = Milestone(
        escrow_id=escrow.id,
        idx=1,
        label="Delivery",
        amount=Decimal("100.00"),
        proof_type="photo",
        validator="SENDER",
        status=MilestoneStatus.APPROVED,
    )
    db_session.add_all([deposit, milestone])
    db_session.flush()

    payment = Payment(
        escrow_id=escrow.id,
        milestone_id=milestone.id,
        amount=Decimal("100.00"),
        status=PaymentStatus.PENDING,
    )
    db_session.add(payment)
    db_session.commit()

    response = await client.post(f"/payments/execute/{payment.id}", headers=admin_headers)
    assert response.status_code == 200

    db_session.expire_all()
    refreshed_escrow = db_session.get(EscrowAgreement, escrow.id)
    assert refreshed_escrow.status == EscrowStatus.RELEASED

    closed_event = (
        db_session.execute(
            select(EscrowEvent)
            .where(EscrowEvent.escrow_id == escrow.id, EscrowEvent.kind == "CLOSED")
            .order_by(EscrowEvent.at.desc())
        )
        .scalars()
        .first()
    )
    assert closed_event is not None
