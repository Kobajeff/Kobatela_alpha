"""Scope enforcement regression tests."""
from uuid import uuid4

import pytest


@pytest.mark.anyio
async def test_sender_cannot_manage_apikeys(client, sender_headers):
    response = await client.get("/apikeys/1", headers=sender_headers)
    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "INSUFFICIENT_SCOPE"


@pytest.mark.anyio
async def test_admin_can_revoke_key(client, admin_headers, make_api_key):
    key_token = f"revokable-{uuid4().hex}"
    api_key = make_api_key(name=f"revokable-{uuid4().hex}", key=key_token)
    response = await client.delete(f"/apikeys/{api_key.id}", headers=admin_headers)
    assert response.status_code in (204, 404)


@pytest.mark.anyio
async def test_sender_forbidden_on_allowlist(client, sender_headers):
    payload = {"owner_id": 1, "recipient_id": 2, "category_id": 3}
    response = await client.post("/allowlist", json=payload, headers=sender_headers)
    assert response.status_code == 403


@pytest.mark.anyio
async def test_admin_allowed_on_allowlist(client, admin_headers):
    owner = await client.post(
        "/users",
        json={"username": f"owner-{uuid4().hex[:8]}", "email": f"owner-{uuid4().hex[:8]}@example.com"},
        headers=admin_headers,
    )
    recipient = await client.post(
        "/users",
        json={"username": f"recipient-{uuid4().hex[:8]}", "email": f"recipient-{uuid4().hex[:8]}@example.com"},
        headers=admin_headers,
    )
    owner_id = owner.json()["id"]
    recipient_id = recipient.json()["id"]

    payload = {"owner_id": owner_id, "recipient_id": recipient_id}
    response = await client.post("/allowlist", json=payload, headers=admin_headers)
    assert response.status_code in (200, 201)


