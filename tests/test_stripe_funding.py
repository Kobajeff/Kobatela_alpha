"""Tests for Stripe funding session and webhook handling."""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.models import FundingRecord, FundingStatus


async def _create_escrow(
    client,
    sender_headers,
    admin_headers,
    amount: str = "100.00",
    currency: str = "USD",
) -> int:
    suffix = uuid4().hex[:8]
    client_user = await client.post(
        "/users",
        json={"username": f"client-{suffix}", "email": f"client-{suffix}@example.com"},
        headers=admin_headers,
    )
    assert client_user.status_code == 201, client_user.text
    provider_user = await client.post(
        "/users",
        json={"username": f"provider-{suffix}", "email": f"provider-{suffix}@example.com"},
        headers=admin_headers,
    )
    assert provider_user.status_code == 201, provider_user.text

    client_user_id = client_user.json()["id"]
    provider_user_id = provider_user.json()["id"]

    escrow_response = await client.post(
        "/escrows",
        json={
            "client_id": client_user_id,
            "provider_id": provider_user_id,
            "amount_total": amount,
            "currency": currency,
            "release_conditions": {"proof": "delivery"},
            "deadline_at": "2030-01-01T00:00:00Z",
        },
        headers=sender_headers,
    )
    assert escrow_response.status_code == 201, escrow_response.text
    return escrow_response.json()["id"]


@pytest.mark.anyio
async def test_funding_session_rejects_when_stripe_disabled(
    client, sender_headers, admin_headers, db_session, monkeypatch
):
    # Ensure table exists even without migration
    FundingRecord.__table__.create(bind=db_session.get_bind(), checkfirst=True)

    class StubSettings:
        STRIPE_ENABLED = False

    monkeypatch.setattr("app.services.funding.get_settings", lambda: StubSettings())

    escrow_id = await _create_escrow(client, sender_headers, admin_headers)

    response = await client.post(
        f"/escrows/{escrow_id}/funding-session", headers=sender_headers
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STRIPE_FUNDING_DISABLED"


@pytest.mark.anyio
async def test_funding_session_creates_record_when_stripe_enabled(
    client, sender_headers, admin_headers, db_session, monkeypatch
):
    FundingRecord.__table__.create(bind=db_session.get_bind(), checkfirst=True)

    class StubSettings:
        STRIPE_ENABLED = True

    class FakePaymentIntent:
        id = "pi_test_123"
        client_secret = "pi_client_secret"

    class FakeStripeClient:
        def __init__(self, settings):
            self.settings = settings

        def create_funding_payment_intent(self, escrow, amount: Decimal, currency: str):
            assert amount == escrow.amount_total
            assert currency == escrow.currency
            return FakePaymentIntent()

    monkeypatch.setattr("app.services.funding.get_settings", lambda: StubSettings())
    monkeypatch.setattr("app.services.funding.StripeClient", FakeStripeClient)

    escrow_id = await _create_escrow(client, sender_headers, admin_headers)

    response = await client.post(
        f"/escrows/{escrow_id}/funding-session", headers=sender_headers
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["client_secret"] == "pi_client_secret"

    funding = db_session.get(FundingRecord, data["funding_id"])
    assert funding is not None
    assert funding.stripe_payment_intent_id == "pi_test_123"
    assert funding.status == FundingStatus.CREATED
    assert funding.amount == Decimal("100.00")


@pytest.mark.anyio
async def test_stripe_webhook_marks_funding_succeeded(client, db_session, monkeypatch):
    FundingRecord.__table__.create(bind=db_session.get_bind(), checkfirst=True)

    stub_settings = type(
        "StubSettings",
        (),
        {
            "STRIPE_ENABLED": True,
            "STRIPE_SECRET_KEY": "sk_test",
            "STRIPE_WEBHOOK_SECRET": "whsec_test",
            "STRIPE_CONNECT_ENABLED": False,
        },
    )()

    calls: list[dict] = []

    class FakeStripeClient:
        def __init__(self, settings):
            self.settings = settings

        def construct_webhook_event(self, payload: bytes, sig_header: str):
            return {
                "id": "evt_123",
                "type": "payment_intent.succeeded",
                "data": {
                    "object": {
                        "id": "pi_succeeded_123",
                        "amount_received": 12345,
                        "currency": "usd",
                        "metadata": {"escrow_id": "42"},
                    }
                },
            }

    def fake_mark_funding_succeeded(db, *, stripe_payment_intent_id: str, amount: Decimal, currency: str):
        calls.append(
            {
                "stripe_payment_intent_id": stripe_payment_intent_id,
                "amount": amount,
                "currency": currency,
            }
        )
        return None

    monkeypatch.setattr("app.services.psp_webhooks._current_settings", lambda: stub_settings)
    monkeypatch.setattr("app.services.psp_webhooks.StripeClient", FakeStripeClient)
    monkeypatch.setattr(
        "app.services.funding.mark_funding_succeeded", fake_mark_funding_succeeded
    )

    response = await client.post(
        "/psp/stripe/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "test-signature"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"received": True}

    assert calls
    assert calls[0]["stripe_payment_intent_id"] == "pi_succeeded_123"
    assert calls[0]["amount"] == Decimal("123.45")
    assert calls[0]["currency"] == "usd"
