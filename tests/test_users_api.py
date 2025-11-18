import pytest
from uuid import uuid4

from app.models.audit import AuditLog


@pytest.mark.anyio("asyncio")
async def test_user_creation_audit_has_api_actor(client, admin_headers, db_session):
    payload = {
        "username": f"audit-user-{uuid4().hex[:6]}",
        "email": f"audit-user-{uuid4().hex[:6]}@example.com",
    }
    resp = await client.post("/users", json=payload, headers=admin_headers)
    assert resp.status_code == 201

    db_session.expire_all()
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "CREATE_USER")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.actor.startswith("apikey:")
