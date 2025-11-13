"""Back-office RBAC checks."""
from uuid import uuid4

import pytest
from sqlalchemy import text

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


@pytest.mark.anyio
async def test_user_creation_emits_audit(client, admin_headers, db_session):
    payload = {"username": f"audited-{uuid4().hex[:6]}", "email": f"audited-{uuid4().hex[:6]}@example.com"}
    response = await client.post("/users", json=payload, headers=admin_headers)
    assert response.status_code == 201

    row = db_session.execute(
        text("SELECT action, entity, data_json FROM audit_logs ORDER BY id DESC LIMIT 1")
    ).fetchone()
    assert row is not None
    assert row[0] == "CREATE_USER"
    assert row[1] == "User"


@pytest.mark.anyio
async def test_sender_forbidden_on_spend_catalogue(client, sender_headers):
    cat_resp = await client.post(
        "/spend/categories",
        json={"code": "CAT-403", "label": "Forbidden"},
        headers=sender_headers,
    )
    merch_resp = await client.post(
        "/spend/merchants",
        json={"name": "Forbidden Merchant", "is_certified": True},
        headers=sender_headers,
    )
    allow_resp = await client.post(
        "/spend/allow",
        json={"owner_id": 1, "merchant_id": 1},
        headers=sender_headers,
    )

    assert cat_resp.status_code == 403
    assert merch_resp.status_code == 403
    assert allow_resp.status_code == 403



@pytest.mark.anyio
async def test_support_allowed_on_spend_catalogue(client, support_headers, db_session):
    user_payload = {"username": f"bo-user-{uuid4().hex[:6]}", "email": f"bo-user-{uuid4().hex[:6]}@example.com"}
    user_resp = await client.post("/users", json=user_payload, headers=support_headers)
    assert user_resp.status_code == 201
    owner_id = user_resp.json()["id"]

    cat_resp = await client.post(
        "/spend/categories",
        json={"code": f"CAT-{uuid4().hex[:4]}", "label": "Support Cat"},
        headers=support_headers,
    )
    assert cat_resp.status_code == 201
    category_id = cat_resp.json()["id"]

    merch_resp = await client.post(
        "/spend/merchants",
        json={
            "name": f"Merchant-{uuid4().hex[:6]}",
            "category_id": category_id,
            "is_certified": True,
        },
        headers=support_headers,
    )
    assert merch_resp.status_code == 201
    merchant_id = merch_resp.json()["id"]

    allow_resp = await client.post(
        "/spend/allow",
        json={"owner_id": owner_id, "merchant_id": merchant_id},
        headers=support_headers,
    )
    assert allow_resp.status_code == 201

    last_log = db_session.execute(
        text("SELECT action, entity FROM audit_logs ORDER BY id DESC LIMIT 1")
    ).fetchone()
    assert last_log is not None
    assert last_log[0] == "SPEND_ALLOW_CREATED"
    assert last_log[1] == "AllowedUsage"
