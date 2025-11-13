"""Scope enforcement regression tests."""
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.security import DEV_API_KEY as LEGACY_TOKEN


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
async def test_legacy_key_rejected_outside_dev(monkeypatch, client):
    monkeypatch.setattr("app.config.DEV_API_KEY_ALLOWED", False, raising=False)
    monkeypatch.setattr("app.security.DEV_API_KEY_ALLOWED", False, raising=False)
    response = await client.post("/mandates/cleanup", headers={"Authorization": f"Bearer {LEGACY_TOKEN}"})
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "LEGACY_KEY_FORBIDDEN"


@pytest.mark.anyio
async def test_legacy_key_usage_is_audited(monkeypatch, client, db_session):
    # S'assurer que les modules utilisent la dernière config (mode dev autorisé)
    monkeypatch.setattr("app.config.DEV_API_KEY_ALLOWED", True, raising=False)
    monkeypatch.setattr("app.security.DEV_API_KEY_ALLOWED", True, raising=False)
    response = await client.post("/mandates/cleanup", headers={"Authorization": f"Bearer {LEGACY_TOKEN}"})
    assert response.status_code == 202
    audit_entry = db_session.execute(
        select(AuditLog).where(AuditLog.action == "LEGACY_API_KEY_USED").order_by(AuditLog.at.desc())
    ).scalars().first()
    assert audit_entry is not None
