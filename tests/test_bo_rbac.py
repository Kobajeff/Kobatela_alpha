"""Back-office RBAC checks."""
from uuid import uuid4

import pytest

from app.models.api_key import ApiScope


@pytest.fixture
def support_headers(make_api_key):
    token = f"support-{uuid4().hex}"
    make_api_key(name=f"support-{uuid4().hex}", key=token, scope=ApiScope.support)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_sender_forbidden_on_users_and_alerts(client, sender_headers):
    user_payload = {"username": f"user-{uuid4().hex[:8]}", "email": f"user-{uuid4().hex[:8]}@example.com"}
    response_user = await client.post("/users", json=user_payload, headers=sender_headers)
    response_alerts = await client.get("/alerts", headers=sender_headers)
    assert response_user.status_code == 403
    assert response_alerts.status_code == 403


@pytest.mark.anyio
async def test_support_allowed_on_alerts(client, support_headers):
    response = await client.get("/alerts", headers=support_headers)
    assert response.status_code == 200
