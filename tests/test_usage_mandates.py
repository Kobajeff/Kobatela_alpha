from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models import UsageMandate, UsageMandateStatus, User
from app.services import mandates as mandate_service


def _idem_headers(base_headers: dict[str, str]) -> dict[str, str]:
    return {**base_headers, "Idempotency-Key": str(uuid4())}


@pytest.mark.anyio("asyncio")
async def test_create_usage_mandate(client, auth_headers):
    sender = await client.post(
        "/users",
        json={"username": "mandate-sender", "email": "sender@example.com"},
        headers=auth_headers,
    )
    beneficiary = await client.post(
        "/users",
        json={"username": "mandate-benef", "email": "benef@example.com"},
        headers=auth_headers,
    )
    assert sender.status_code == 201
    assert beneficiary.status_code == 201

    expires_at = (datetime.now(tz=UTC) + timedelta(days=10)).isoformat()
    payload = {
        "sender_id": sender.json()["id"],
        "beneficiary_id": beneficiary.json()["id"],
        "total_amount": "100.00",
        "currency": "USD",
        "allowed_category_id": None,
        "allowed_merchant_id": None,
        "expires_at": expires_at,
    }

    response = await client.post("/mandates", json=payload, headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ACTIVE"
    assert body["total_amount"] == "100.00"


@pytest.mark.anyio("asyncio")
async def test_purchase_blocked_without_mandate(client, auth_headers):
    sender = await client.post(
        "/users",
        json={"username": "nomandate-sender", "email": "nomandate-sender@example.com"},
        headers=auth_headers,
    )
    assert sender.status_code == 201

    user = await client.post(
        "/users",
        json={"username": "nomandate", "email": "nomandate@example.com"},
        headers=auth_headers,
    )
    merchant = await client.post(
        "/spend/merchants",
        json={"name": "Mandate Shop", "is_certified": False},
        headers=auth_headers,
    )
    assert user.status_code == 201
    assert merchant.status_code == 201

    purchase = await client.post(
        "/spend/purchases",
        json={
            "sender_id": sender.json()["id"],
            "beneficiary_id": user.json()["id"],
            "merchant_id": merchant.json()["id"],
            "amount": 10.0,
            "currency": "USD",
        },
        headers=_idem_headers(auth_headers),
    )
    assert purchase.status_code == 403
    assert purchase.json()["error"]["code"] == "MANDATE_REQUIRED"


@pytest.mark.anyio("asyncio")
async def test_purchase_allowed_under_mandate(client, auth_headers):
    beneficiary = await client.post(
        "/users",
        json={"username": "mandate-benef2", "email": "benef2@example.com"},
        headers=auth_headers,
    )
    sender = await client.post(
        "/users",
        json={"username": "mandate-sender2", "email": "sender2@example.com"},
        headers=auth_headers,
    )
    merchant = await client.post(
        "/spend/merchants",
        json={"name": "Allowed Mandate Merchant", "is_certified": True},
        headers=auth_headers,
    )

    assert beneficiary.status_code == 201
    assert sender.status_code == 201
    assert merchant.status_code == 201

    expires_at = (datetime.now(tz=UTC) + timedelta(days=5)).isoformat()
    mandate_payload = {
        "sender_id": sender.json()["id"],
        "beneficiary_id": beneficiary.json()["id"],
        "total_amount": "50.00",
        "currency": "USD",
        "allowed_category_id": None,
        "allowed_merchant_id": merchant.json()["id"],
        "expires_at": expires_at,
    }
    mandate = await client.post("/mandates", json=mandate_payload, headers=auth_headers)
    assert mandate.status_code == 201

    purchase = await client.post(
        "/spend/purchases",
        json={
            "sender_id": sender.json()["id"],
            "beneficiary_id": beneficiary.json()["id"],
            "merchant_id": merchant.json()["id"],
            "amount": 25.0,
            "currency": "USD",
        },
        headers=_idem_headers(auth_headers),
    )
    assert purchase.status_code == 201
    assert purchase.json()["status"] == "COMPLETED"


@pytest.mark.anyio("asyncio")
async def test_purchase_denied_by_mandate_restrictions(client, auth_headers):
    beneficiary = await client.post(
        "/users",
        json={"username": "mandate-benef3", "email": "benef3@example.com"},
        headers=auth_headers,
    )
    sender = await client.post(
        "/users",
        json={"username": "mandate-sender3", "email": "sender3@example.com"},
        headers=auth_headers,
    )
    allowed_merchant = await client.post(
        "/spend/merchants",
        json={"name": "Mandate Merchant A", "is_certified": True},
        headers=auth_headers,
    )
    blocked_merchant = await client.post(
        "/spend/merchants",
        json={"name": "Mandate Merchant B", "is_certified": True},
        headers=auth_headers,
    )

    expires_at = (datetime.now(tz=UTC) + timedelta(days=5)).isoformat()
    mandate_payload = {
        "sender_id": sender.json()["id"],
        "beneficiary_id": beneficiary.json()["id"],
        "total_amount": "60.00",
        "currency": "USD",
        "allowed_category_id": None,
        "allowed_merchant_id": allowed_merchant.json()["id"],
        "expires_at": expires_at,
    }
    mandate = await client.post("/mandates", json=mandate_payload, headers=auth_headers)
    assert mandate.status_code == 201

    denied = await client.post(
        "/spend/purchases",
        json={
            "sender_id": sender.json()["id"],
            "beneficiary_id": beneficiary.json()["id"],
            "merchant_id": blocked_merchant.json()["id"],
            "amount": 5.0,
            "currency": "USD",
        },
        headers=_idem_headers(auth_headers),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "MANDATE_MERCHANT_FORBIDDEN"


def test_close_expired_mandates(db_session):
    sender = User(username="cron-sender", email="cron-sender@example.com")
    beneficiary = User(username="cron-benef", email="cron-benef@example.com")
    db_session.add_all([sender, beneficiary])
    db_session.flush()

    mandate = UsageMandate(
        sender_id=sender.id,
        beneficiary_id=beneficiary.id,
        total_amount=Decimal("30.00"),
        currency="USD",
        allowed_category_id=None,
        allowed_merchant_id=None,
        expires_at=datetime.now(tz=UTC) - timedelta(days=1),
        status=UsageMandateStatus.ACTIVE,
    )
    db_session.add(mandate)
    db_session.commit()

    updated = mandate_service.close_expired_mandates(db_session)
    assert updated == 1

    db_session.refresh(mandate)
    assert mandate.status is UsageMandateStatus.EXPIRED


@pytest.mark.anyio("asyncio")
async def test_purchase_rejects_different_sender(
    client,
    auth_headers,
    make_users_merchants_mandate,
):
    sender_user, beneficiary_user, merchant_id = make_users_merchants_mandate(
        total="50.00",
        currency="EUR",
    )

    wrong_sender = await client.post(
        "/users",
        json={"username": "wrong-sender", "email": "wrong-sender@example.com"},
        headers=auth_headers,
    )
    assert wrong_sender.status_code == 201

    response = await client.post(
        "/spend/purchases",
        json={
            "sender_id": wrong_sender.json()["id"],
            "beneficiary_id": beneficiary_user.id,
            "merchant_id": merchant_id,
            "amount": "20.00",
            "currency": "EUR",
        },
        headers=_idem_headers(auth_headers),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "MANDATE_REQUIRED"


@pytest.mark.anyio("asyncio")
async def test_concurrent_spends_are_atomic(
    client,
    auth_headers,
    make_users_merchants_mandate,
):
    sender_user, beneficiary_user, merchant_id = make_users_merchants_mandate(
        total="30.00",
        currency="USD",
    )

    payload = {
        "sender_id": sender_user.id,
        "beneficiary_id": beneficiary_user.id,
        "merchant_id": merchant_id,
        "amount": "20.00",
        "currency": "USD",
    }

    first = await client.post(
        "/spend/purchases",
        json=payload,
        headers={**auth_headers, "Idempotency-Key": "mandate-k1"},
    )
    second = await client.post(
        "/spend/purchases",
        json=payload,
        headers={**auth_headers, "Idempotency-Key": "mandate-k2"},
    )

    codes = sorted([first.status_code, second.status_code])
    assert codes == [201, 409]
