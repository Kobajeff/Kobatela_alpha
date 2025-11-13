"""Regression tests for escrow finalization commit."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import AuditLog, EscrowAgreement, EscrowEvent, EscrowStatus, Milestone, MilestoneStatus, User
from app.services.payments import _finalize_escrow_if_paid


@pytest.mark.anyio
async def test_finalize_escrow_commits_and_emits_event(db_session):
    now = datetime.now(tz=UTC)
    client = User(username=f"client-{uuid4().hex[:8]}", email=f"client-{uuid4().hex[:8]}@example.com")
    provider = User(username=f"provider-{uuid4().hex[:8]}", email=f"provider-{uuid4().hex[:8]}@example.com")
    db_session.add_all([client, provider])
    db_session.flush()

    escrow = EscrowAgreement(
        client_id=client.id,
        provider_id=provider.id,
        amount_total=Decimal("100.00"),
        currency="USD",
        status=EscrowStatus.RELEASABLE,
        release_conditions_json={"type": "auto"},
        deadline_at=now + timedelta(days=7),
    )
    db_session.add(escrow)
    db_session.flush()

    milestone = Milestone(
        escrow_id=escrow.id,
        idx=1,
        label="Delivery",
        amount=Decimal("100.00"),
        proof_type="photo",
        validator="SENDER",
        status=MilestoneStatus.PAID,
    )
    db_session.add(milestone)
    db_session.commit()

    _finalize_escrow_if_paid(db_session, escrow.id)

    db_session.expire_all()
    refreshed = db_session.get(EscrowAgreement, escrow.id)
    assert refreshed.status == EscrowStatus.RELEASED

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
    audit_entry = (
        db_session.execute(
            select(AuditLog)
            .where(AuditLog.action == "ESCROW_RELEASED", AuditLog.entity_id == escrow.id)
            .order_by(AuditLog.at.desc())
        )
        .scalars()
        .first()
    )
    assert audit_entry is not None
