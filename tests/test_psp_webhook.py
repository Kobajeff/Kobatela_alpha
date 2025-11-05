"""Tests for PSP webhook processing."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import timedelta

import pytest

from app.models import (
    EscrowAgreement,
    EscrowStatus,
    Payment,
    PaymentStatus,
    PSPWebhookEvent,
    User,
)
from app.utils.time import utcnow


def _create_user(db_session, username: str) -> User:
    user = User(username=username, email=f"{username}@example.com")
    db_session.add(user)
    db_session.flush()
    return user


@pytest.mark.anyio
async def test_psp_webhook_settles_payment(client, db_session):
    """A PSP settlement webhook should mark the payment as settled and be idempotent."""

    client_user = _create_user(db_session, "client-webhook")
    provider_user = _create_user(db_session, "provider-webhook")
    escrow = EscrowAgreement(
        client_id=client_user.id,
        provider_id=provider_user.id,
        amount_total=100.0,
        currency="USD",
        status=EscrowStatus.FUNDED,
        release_conditions_json={},
        deadline_at=utcnow() + timedelta(days=7),
    )
    db_session.add(escrow)
    db_session.flush()

    payment = Payment(
        escrow_id=escrow.id,
        milestone_id=None,
        amount=50.0,
        status=PaymentStatus.SENT,
        psp_ref="psp-123",
        idempotency_key="pay-psp-123",
    )
    db_session.add(payment)
    db_session.commit()

    payload = {"type": "payment.settled", "psp_ref": "psp-123"}
    body = json.dumps(payload).encode()
    signature = hmac.new(os.environ["PSP_WEBHOOK_SECRET"].encode(), body, hashlib.sha256).hexdigest()

    response = await client.post(
        "/psp/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-PSP-Signature": signature,
            "X-PSP-Event-Id": "evt-psp-1",
            "X-PSP-Ref": "psp-123",
        },
    )
    assert response.status_code == 200
    db_session.refresh(payment)
    assert payment.status == PaymentStatus.SETTLED
    assert db_session.query(PSPWebhookEvent).count() == 1

    repeat = await client.post(
        "/psp/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-PSP-Signature": signature,
            "X-PSP-Event-Id": "evt-psp-1",
            "X-PSP-Ref": "psp-123",
        },
    )
    assert repeat.status_code == 200
    assert db_session.query(PSPWebhookEvent).count() == 1


@pytest.mark.anyio
async def test_psp_webhook_invalid_signature(client):
    """An invalid signature should be rejected."""

    payload = {"type": "payment.settled"}
    body = json.dumps(payload).encode()

    response = await client.post(
        "/psp/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-PSP-Signature": "bad-signature",
            "X-PSP-Event-Id": "evt-psp-2",
        },
    )
    assert response.status_code == 401
