"""Idempotency behaviour for spend endpoint."""
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.allowed_payee import AllowedPayee
from app.models.escrow import EscrowAgreement, EscrowDeposit, EscrowStatus
from app.models.user import User


def _prepare_usage_context(db_session):
    now = datetime.now(tz=UTC)
    sender = User(username=f"sender-{uuid4().hex[:8]}", email=f"sender-{uuid4().hex[:8]}@example.com")
    provider = User(username=f"provider-{uuid4().hex[:8]}", email=f"provider-{uuid4().hex[:8]}@example.com")
    db_session.add_all([sender, provider])
    db_session.flush()

    escrow = EscrowAgreement(
        client_id=sender.id,
        provider_id=provider.id,
        amount_total=Decimal("200.00"),
        currency="USD",
        status=EscrowStatus.FUNDED,
        release_conditions_json={"type": "usage"},
        deadline_at=now,
    )
    db_session.add(escrow)
    db_session.flush()

    deposit = EscrowDeposit(escrow_id=escrow.id, amount=Decimal("200.00"), idempotency_key=f"dep-{uuid4().hex[:8]}")
    payee = AllowedPayee(
        escrow_id=escrow.id,
        payee_ref="PAYEE-1",
        label="Trusted Payee",
        daily_limit=Decimal("500.00"),
        total_limit=Decimal("500.00"),
        spent_today=Decimal("0"),
        spent_total=Decimal("0"),
        last_reset_at=now.date(),
    )
    db_session.add_all([deposit, payee])
    db_session.commit()

    return escrow


@pytest.mark.anyio
async def test_spend_requires_idempotency_key(client, sender_headers, db_session):
    escrow = _prepare_usage_context(db_session)

    payload = {"escrow_id": escrow.id, "payee_ref": "PAYEE-1", "amount": "10.00"}
    response = await client.post("/spend", json=payload, headers=sender_headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


@pytest.mark.anyio
async def test_spend_with_idempotency_key_is_idempotent(client, sender_headers, db_session):
    escrow = _prepare_usage_context(db_session)

    payload = {"escrow_id": escrow.id, "payee_ref": "PAYEE-1", "amount": "10.00"}
    idem_key = uuid4().hex
    headers = {**sender_headers, "Idempotency-Key": idem_key}
    first = await client.post("/spend", json=payload, headers=headers)
    second = await client.post("/spend", json=payload, headers=headers)

    assert first.status_code in (200, 201)
    assert second.status_code in (200, 201)
    assert first.json()["payment_id"] == second.json()["payment_id"]
