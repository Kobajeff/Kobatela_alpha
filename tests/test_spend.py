from datetime import UTC, datetime, timedelta
from uuid import uuid4

from decimal import Decimal

import pytest

from app.models import Merchant, Purchase, PurchaseStatus, UsageMandate, UsageMandateStatus, User
from app.models.audit import AuditLog
from app.schemas.spend import PurchaseCreate
from app.services import spend as spend_service


def _idem_headers(base_headers: dict[str, str]) -> dict[str, str]:
    return {**base_headers, "Idempotency-Key": str(uuid4())}


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
        headers=_idem_headers(auth_headers),
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
        headers=_idem_headers(auth_headers),
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
        headers=_idem_headers(auth_headers),
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


@pytest.mark.anyio("asyncio")
async def test_purchase_requires_idempotency_header(client, auth_headers):
    payload = {
        "sender_id": 1,
        "beneficiary_id": 2,
        "merchant_id": 3,
        "amount": 15.0,
        "currency": "USD",
    }

    response = await client.post(
        "/spend/purchases",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 422


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


def test_purchase_amount_normalized_to_two_decimals(db_session):
    sender = User(username="spender", email="spender@example.com")
    beneficiary = User(username="spender-benef", email="spender-benef@example.com")
    merchant = Merchant(name="Rounding Shop", is_certified=True)
    db_session.add_all([sender, beneficiary, merchant])
    db_session.flush()

    mandate = UsageMandate(
        sender_id=sender.id,
        beneficiary_id=beneficiary.id,
        total_amount=Decimal("100.00"),
        currency="USD",
        allowed_category_id=None,
        allowed_merchant_id=merchant.id,
        expires_at=datetime.now(tz=UTC) + timedelta(days=5),
        status=UsageMandateStatus.ACTIVE,
    )
    db_session.add(mandate)
    db_session.commit()

    payload = PurchaseCreate(
        sender_id=sender.id,
        beneficiary_id=beneficiary.id,
        merchant_id=merchant.id,
        amount=Decimal("33.335"),
        currency="USD",
    )
    purchase = spend_service.create_purchase(
        db_session, payload, idempotency_key=str(uuid4())
    )
    db_session.refresh(mandate)

    assert purchase.amount == Decimal("33.34")
    assert mandate.total_spent == Decimal("33.34")


@pytest.mark.anyio("asyncio")
async def test_spend_category_audit_records_api_actor(client, admin_headers, db_session):
    payload = {"code": f"CAT-{uuid4().hex[:6]}", "label": "Monitored"}
    resp = await client.post("/spend/categories", json=payload, headers=admin_headers)
    assert resp.status_code == 201

    db_session.expire_all()
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "SPEND_CATEGORY_CREATED")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.actor.startswith("apikey:")
