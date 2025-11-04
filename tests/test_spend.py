from uuid import uuid4

import pytest


@pytest.mark.anyio("asyncio")
async def test_purchase_requires_authorization(client, auth_headers):
    user = await client.post("/users", json={"username": "buyer", "email": "buyer@example.com"}, headers=auth_headers)
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
            "sender_id": user_id,
            "merchant_id": merchant_id,
            "amount": 42.0,
            "currency": "USD",
        },
        headers=auth_headers,
    )
    assert unauthorized.status_code == 403
    assert unauthorized.json()["error"]["code"] == "UNAUTHORIZED_USAGE"

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
            "sender_id": user_id,
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
    user = await client.post("/users", json={"username": "catbuyer", "email": "catbuyer@example.com"}, headers=auth_headers)
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
    purchase = await client.post(
        "/spend/purchases",
        json={
            "sender_id": user_id,
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
            "sender_id": user_id,
            "merchant_id": merchant_id,
            "amount": 15.5,
            "currency": "EUR",
        },
        headers={**auth_headers, "Idempotency-Key": key},
    )
    assert retry.status_code == 201
    assert retry.json()["id"] == purchase_id
