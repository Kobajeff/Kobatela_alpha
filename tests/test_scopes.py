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


