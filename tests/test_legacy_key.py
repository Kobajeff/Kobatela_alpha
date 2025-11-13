"""Tests de la clé legacy DEV."""
import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
import app.security as security_mod


@pytest.mark.anyio
async def test_legacy_rejected_outside_dev(monkeypatch, client):
    legacy_value = "legacy-test-key"
    monkeypatch.setattr("app.config.DEV_API_KEY", legacy_value, raising=False)
    monkeypatch.setattr("app.security.DEV_API_KEY", legacy_value, raising=False)
    monkeypatch.setattr("app.utils.apikey.DEV_API_KEY", legacy_value, raising=False)
    monkeypatch.setitem(security_mod.require_api_key.__globals__, "DEV_API_KEY", legacy_value)
    monkeypatch.setattr("app.config.DEV_API_KEY_ALLOWED", False, raising=False)
    monkeypatch.setattr("app.security.DEV_API_KEY_ALLOWED", False, raising=False)
    monkeypatch.setattr("app.utils.apikey.DEV_API_KEY_ALLOWED", False, raising=False)
    monkeypatch.setitem(security_mod.require_api_key.__globals__, "DEV_API_KEY_ALLOWED", False)

    response = await client.get(
        "/transactions/1",
        headers={"Authorization": f"Bearer {legacy_value}"},
    )
    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["code"] == "LEGACY_KEY_FORBIDDEN"


@pytest.mark.anyio
async def test_legacy_accepted_in_dev_and_audited(monkeypatch, client, db_session):
    legacy_value = "legacy-dev-key"
    monkeypatch.setattr("app.config.DEV_API_KEY", legacy_value, raising=False)
    monkeypatch.setattr("app.security.DEV_API_KEY", legacy_value, raising=False)
    monkeypatch.setattr("app.utils.apikey.DEV_API_KEY", legacy_value, raising=False)
    monkeypatch.setitem(security_mod.require_api_key.__globals__, "DEV_API_KEY", legacy_value)
    monkeypatch.setattr("app.config.DEV_API_KEY_ALLOWED", True, raising=False)
    monkeypatch.setattr("app.security.DEV_API_KEY_ALLOWED", True, raising=False)
    monkeypatch.setattr("app.utils.apikey.DEV_API_KEY_ALLOWED", True, raising=False)
    monkeypatch.setitem(security_mod.require_api_key.__globals__, "DEV_API_KEY_ALLOWED", True)

    response = await client.get(
        "/transactions/1",
        headers={"Authorization": f"Bearer {legacy_value}"},
    )
    assert response.status_code in (200, 204, 404)

    audit_entry = (
        db_session.execute(
            select(AuditLog)
            .where(AuditLog.action == "LEGACY_API_KEY_USED")
            .order_by(AuditLog.at.desc())
        )
        .scalars()
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.data_json.get("env") in {"dev", "local", "dev_local"}
