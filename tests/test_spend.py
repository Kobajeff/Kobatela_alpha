from datetime import UTC, datetime, timedelta
from uuid import uuid4

from decimal import Decimal

import pytest

from app.models import Merchant, Purchase, PurchaseStatus, User


@pytest.mark.anyio("asyncio")
async def test_purchase_requires_authorization(client, auth_headers):
    sender = await client.post(
        "/users",
        json={"username": "diaspora", "email": "diaspora@example.com"},
        headers=auth_headers,
    )
    assert sender.status_code == 201
    sender_id = sender.json()["id"]

    user = await client.post(
        "/users",
        json={"username": "buyer", "email": "buyer@example.com"},
        headers=auth_headers,
    )
    assert user.status_code == 201
    user_id = user.json()["id"]

    merchant = await client.post(
        "/spend/merchants",
        json={"name": "Shop", "is_certified": False},
        headers=auth_headers,
    )
    assert merchant.status_code == 201
    merchant_id = merchant.json()["id"]

    unauthorized = await client.post(
        "/spend/purchases",
        json={
            "sender_id": sender_id,
            "beneficiary_id": user_id,
            "merchant_id": merchant_id,
            "amount": 42.0,
            "currency": "USD",
        },
        headers=auth_headers,
    )
    assert unauthorized.status_code == 403
    assert unauthorized.json()["error"]["code"] == "MANDATE_REQUIRED"

    future_expiry = datetime.now(tz=UTC) + timedelta(days=7)
    mandate = await client.post(
        "/mandates",
        json={
            "sender_id": sender_id,
            "beneficiary_id": user_id,
            "total_amount": "150.00",
            "currency": "USD",
            "allowed_category_id": None,
            "allowed_merchant_id": None,
            "expires_at": future_expiry.isoformat(),
        },
        headers=auth_headers,
    )
    assert mandate.status_code == 201

    unauthorized_usage = await client.post(
        "/spend/purchases",
        json={
            "sender_id": sender_id,
            "beneficiary_id": user_id,
            "merchant_id": merchant_id,
            "amount": 10.0,
            "currency": "USD",
        },
        headers=auth_headers,
    )
    assert unauthorized_usage.status_code == 403
    assert unauthorized_usage.json()["error"]["code"] == "UNAUTHORIZED_USAGE"

    allow = await client.post(
        "/spend/allow",
        json={"owner_id": user_id, "merchant_id": merchant_id},
        headers=auth_headers,
    )
    assert allow.status_code == 201
    assert allow.json()["status"] in {"added", "exists"}

    purchase = await client.post(
        "/spend/purchases",
        json={
            "sender_id": sender_id,
            "beneficiary_id": user_id,
            "merchant_id": merchant_id,
            "amount": 42.0,
            "currency": "USD",
        },
        headers=auth_headers,
    )
    assert purchase.status_code == 201
    assert purchase.json()["status"] == "COMPLETED"


@pytest.mark.anyio("asyncio")
async def test_purchase_by_category_and_idempotency(client, auth_headers):
    sender = await client.post(
        "/users",
        json={"username": "diaspora-cat", "email": "diaspora-cat@example.com"},
        headers=auth_headers,
    )
    assert sender.status_code == 201
    sender_id = sender.json()["id"]

    user = await client.post(
        "/users",
        json={"username": "catbuyer", "email": "catbuyer@example.com"},
        headers=auth_headers,
    )
    assert user.status_code == 201
    user_id = user.json()["id"]

    category = await client.post(
        "/spend/categories",
        json={"code": "DIGITAL", "label": "Digital Goods"},
        headers=auth_headers,
    )
    assert category.status_code == 201
    category_id = category.json()["id"]

    merchant = await client.post(
        "/spend/merchants",
        json={"name": "StreamBox", "category_id": category_id, "is_certified": False},
        headers=auth_headers,
    )
    assert merchant.status_code == 201
    merchant_id = merchant.json()["id"]

    allow = await client.post(
        "/spend/allow",
        json={"owner_id": user_id, "category_id": category_id},
        headers=auth_headers,
    )
    assert allow.status_code == 201
    assert allow.json()["status"] in {"added", "exists"}

    key = str(uuid4())
    future_expiry = datetime.now(tz=UTC) + timedelta(days=7)
    mandate = await client.post(
        "/mandates",
        json={
            "sender_id": sender_id,
            "beneficiary_id": user_id,
            "total_amount": "200.00",
            "currency": "EUR",
            "allowed_category_id": category_id,
            "allowed_merchant_id": None,
            "expires_at": future_expiry.isoformat(),
        },
        headers=auth_headers,
    )
    assert mandate.status_code == 201

    purchase = await client.post(
        "/spend/purchases",
        json={
            "sender_id": sender_id,
            "beneficiary_id": user_id,
            "merchant_id": merchant_id,
            "amount": 15.5,
            "currency": "EUR",
        },
        headers={**auth_headers, "Idempotency-Key": key},
    )
    assert purchase.status_code == 201
    purchase_id = purchase.json()["id"]
    assert purchase.json()["category_id"] == category_id

    retry = await client.post(
        "/spend/purchases",
        json={
            "sender_id": sender_id,
            "beneficiary_id": user_id,
            "merchant_id": merchant_id,
            "amount": 15.5,
            "currency": "EUR",
        },
        headers={**auth_headers, "Idempotency-Key": key},
    )
    assert retry.status_code == 201
    assert retry.json()["id"] == purchase_id


def test_purchase_amount_persisted_as_decimal(db_session):
    """The ORM should materialise purchase amounts as Decimal objects."""

    sender = User(username="decimal-buyer", email="buyer-decimal@example.com")
    merchant = Merchant(name="Decimal Shop", is_certified=True)
    db_session.add_all([sender, merchant])
    db_session.flush()

    purchase = Purchase(
        sender_id=sender.id,
        merchant_id=merchant.id,
        category_id=None,
        amount=Decimal("42.17"),
        currency="USD",
        status=PurchaseStatus.COMPLETED,
    )
    db_session.add(purchase)
    db_session.commit()
    db_session.refresh(purchase)

    assert isinstance(purchase.amount, Decimal)
    assert purchase.amount == Decimal("42.17")
