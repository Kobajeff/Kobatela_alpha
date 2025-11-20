"""Tests for PSP webhook processing."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import hashlib
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.main import _assert_psp_webhook_secrets
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

    db_session.query(PSPWebhookEvent).delete()
    db_session.commit()
    assert db_session.query(PSPWebhookEvent).count() == 0

    client_user = _create_user(db_session, "client-webhook")
    provider_user = _create_user(db_session, "provider-webhook")
    escrow = EscrowAgreement(
        client_id=client_user.id,
        provider_id=provider_user.id,
        amount_total=Decimal("100.00"),
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
        amount=Decimal("50.00"),
        status=PaymentStatus.SENT,
        psp_ref="psp-123",
        idempotency_key="pay-psp-123",
    )
    db_session.add(payment)
    db_session.commit()

    payload = {"type": "payment.settled", "psp_ref": "psp-123"}
    body = json.dumps(payload).encode()
    timestamp = str(utcnow().timestamp())
    payload_to_sign = timestamp.encode() + b"." + body
    signature = hmac.new(os.environ["PSP_WEBHOOK_SECRET"].encode(), payload_to_sign, hashlib.sha256).hexdigest()

    response = await client.post(
        "/psp/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-PSP-Signature": signature,
            "X-PSP-Timestamp": timestamp,
            "X-PSP-Event-Id": "evt-psp-1",
            "X-PSP-Ref": "psp-123",
        },
    )
    assert response.status_code == 200, response.text
    db_session.refresh(payment)
    assert payment.status == PaymentStatus.SETTLED
    assert db_session.query(PSPWebhookEvent).count() == 1

    repeat = await client.post(
        "/psp/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-PSP-Signature": signature,
            "X-PSP-Timestamp": timestamp,
            "X-PSP-Event-Id": "evt-psp-1",
            "X-PSP-Ref": "psp-123",
        },
    )
    assert repeat.status_code == 409
    assert repeat.json()["error"]["code"] == "WEBHOOK_REPLAY"
    assert db_session.query(PSPWebhookEvent).count() == 1


@pytest.mark.anyio
async def test_psp_webhook_accepts_next_secret(client, db_session):
    settings = get_settings()
    db_session.query(PSPWebhookEvent).delete()
    db_session.commit()
    assert db_session.query(PSPWebhookEvent).count() == 0
    original_secret = settings.psp_webhook_secret
    original_next = settings.psp_webhook_secret_next
    try:
        settings.psp_webhook_secret = None
        settings.psp_webhook_secret_next = "next-secret"
        payload = {"type": "payment.settled"}
        body = json.dumps(payload).encode()
        timestamp = str(utcnow().timestamp())
        payload_to_sign = timestamp.encode() + b"." + body
        signature = hmac.new(
            settings.psp_webhook_secret_next.encode(),
            payload_to_sign,
            hashlib.sha256,
        ).hexdigest()

        response = await client.post(
            "/psp/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-PSP-Signature": signature,
                "X-PSP-Timestamp": timestamp,
                "X-PSP-Event-Id": "evt-rot", 
            },
        )
        assert response.status_code == 200, response.text
    finally:
        settings.psp_webhook_secret = original_secret
        settings.psp_webhook_secret_next = original_next


@pytest.mark.anyio
async def test_psp_webhook_invalid_signature(client):
    """An invalid signature should be rejected."""

    payload = {"type": "payment.settled"}
    body = json.dumps(payload).encode()
    timestamp = str(utcnow().timestamp())

    response = await client.post(
        "/psp/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-PSP-Signature": "bad-signature",
            "X-PSP-Timestamp": timestamp,
            "X-PSP-Event-Id": "evt-psp-2",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "WEBHOOK_SIGNATURE_INVALID"


@pytest.mark.anyio
async def test_psp_webhook_timestamp_out_of_range(client):
    payload = {"type": "payment.settled"}
    body = json.dumps(payload).encode()
    timestamp = str(time.time() - 500)
    payload_to_sign = timestamp.encode() + b"." + body
    secret = os.environ["PSP_WEBHOOK_SECRET"].encode()
    signature = hmac.new(secret, payload_to_sign, hashlib.sha256).hexdigest()

    response = await client.post(
        "/psp/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-PSP-Signature": signature,
            "X-PSP-Timestamp": timestamp,
            "X-PSP-Event-Id": "evt-old-ts",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "WEBHOOK_TIMESTAMP_OUT_OF_RANGE"


@pytest.mark.anyio
async def test_psp_webhook_missing_event_id(client):
    payload = {"type": "payment.settled"}
    body = json.dumps(payload).encode()
    timestamp = str(time.time())
    payload_to_sign = timestamp.encode() + b"." + body
    secret = os.environ["PSP_WEBHOOK_SECRET"].encode()
    signature = hmac.new(secret, payload_to_sign, hashlib.sha256).hexdigest()

    response = await client.post(
        "/psp/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-PSP-Signature": signature,
            "X-PSP-Timestamp": timestamp,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MISSING_EVENT_ID"


@pytest.mark.anyio
async def test_psp_webhook_missing_secret(client):
    """The PSP webhook should fail-fast if the secret is not configured."""

    settings = get_settings()
    original_secret = settings.psp_webhook_secret
    try:
        settings.psp_webhook_secret = None
        response = await client.post(
            "/psp/webhook",
            content=b"{}",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 503
    finally:
        settings.psp_webhook_secret = original_secret


def test_psp_secrets_refresh_each_call(monkeypatch):
    from app.services import psp_webhooks

    first = SimpleNamespace(
        psp_webhook_secret="alpha",
        psp_webhook_secret_next=None,
        psp_webhook_max_drift_seconds=300,
    )
    second = SimpleNamespace(
        psp_webhook_secret="beta",
        psp_webhook_secret_next="next-beta",
        psp_webhook_max_drift_seconds=300,
    )

    monkeypatch.setattr(psp_webhooks, "get_settings", lambda: first)
    assert psp_webhooks._current_secrets() == ("alpha", None)

    monkeypatch.setattr(psp_webhooks, "get_settings", lambda: second)
    assert psp_webhooks._current_secrets() == ("beta", "next-beta")


def test_startup_requires_psp_secrets_non_dev():
    prod_like = SimpleNamespace(app_env="prod", psp_webhook_secret=None, psp_webhook_secret_next=None)
    with pytest.raises(RuntimeError):
        _assert_psp_webhook_secrets(prod_like)

    dev_like = SimpleNamespace(app_env="dev", psp_webhook_secret=None, psp_webhook_secret_next=None)
    _assert_psp_webhook_secrets(dev_like)
