from uuid import uuid4

import pytest

from app.services.transactions import ALERT_UNAUTHORIZED


@pytest.mark.anyio("asyncio")
async def test_transaction_authorization_and_idempotency(client, auth_headers):
    # Create users
    sender = await client.post("/users", json={"username": "alice", "email": "alice@example.com"}, headers=auth_headers)
    receiver = await client.post("/users", json={"username": "bob", "email": "bob@example.com"}, headers=auth_headers)
    sender_id = sender.json()["id"]
    receiver_id = receiver.json()["id"]

    # Unauthorized transfer attempt
    response = await client.post(
        "/transactions",
        json={"sender_id": sender_id, "receiver_id": receiver_id, "amount": 100.0, "currency": "USD"},
        headers=auth_headers,
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "UNAUTHORIZED_TRANSFER"

    # Alert created
    alerts = await client.get(f"/alerts", params={"type": ALERT_UNAUTHORIZED}, headers=auth_headers)
    assert alerts.status_code == 200
    assert len(alerts.json()) == 1

    # Allowlist receiver
    allowlist_response = await client.post(
        "/allowlist",
        json={"owner_id": sender_id, "recipient_id": receiver_id},
        headers=auth_headers,
    )
    assert allowlist_response.status_code == 201

    # Authorized transfer
    idempotency_key = str(uuid4())
    response = await client.post(
        "/transactions",
        json={"sender_id": sender_id, "receiver_id": receiver_id, "amount": 100.0, "currency": "USD"},
        headers={**auth_headers, "Idempotency-Key": idempotency_key},
    )
    assert response.status_code == 201
    transaction_id = response.json()["id"]
    assert response.json()["status"] == "COMPLETED"

    # Idempotent retry returns same transaction
    retry = await client.post(
        "/transactions",
        json={"sender_id": sender_id, "receiver_id": receiver_id, "amount": 100.0, "currency": "USD"},
        headers={**auth_headers, "Idempotency-Key": idempotency_key},
    )
    assert retry.status_code == 201
    assert retry.json()["id"] == transaction_id

    # Retrieve transaction
    fetched = await client.get(f"/transactions/{transaction_id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == transaction_id


@pytest.mark.anyio("asyncio")
async def test_transaction_with_certified_receiver(client, auth_headers):
    client_user = await client.post("/users", json={"username": "carol", "email": "carol@example.com"}, headers=auth_headers)
    provider_user = await client.post(
        "/users", json={"username": "dave", "email": "dave@example.com"}, headers=auth_headers
    )
    provider_id = provider_user.json()["id"]

    certify = await client.post(
        "/certified",
        json={"user_id": provider_id, "level": "gold"},
        headers=auth_headers,
    )
    assert certify.status_code == 201

    response = await client.post(
        "/transactions",
        json={
            "sender_id": client_user.json()["id"],
            "receiver_id": provider_id,
            "amount": 250.0,
            "currency": "EUR",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["status"] == "COMPLETED"
