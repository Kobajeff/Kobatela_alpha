"""Audit tests for allowlist and certification endpoints."""
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog


@pytest.mark.anyio
async def test_allowlist_add_emits_audit(client, admin_headers, db_session):
    owner_payload = {"username": f"owner-{uuid4().hex[:8]}", "email": f"owner-{uuid4().hex[:8]}@example.com"}
    recipient_payload = {"username": f"recipient-{uuid4().hex[:8]}", "email": f"recipient-{uuid4().hex[:8]}@example.com"}
    owner = await client.post("/users", json=owner_payload, headers=admin_headers)
    recipient = await client.post("/users", json=recipient_payload, headers=admin_headers)
    owner_id = owner.json()["id"]
    recipient_id = recipient.json()["id"]

    response = await client.post(
        "/allowlist",
        json={"owner_id": owner_id, "recipient_id": recipient_id},
        headers=admin_headers,
    )
    assert response.status_code == 201
    audit_entry = (
        db_session.execute(
            select(AuditLog)
            .where(AuditLog.action == "ALLOWLIST_ADD")
            .order_by(AuditLog.at.desc())
        )
        .scalars()
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.data_json["owner_id"] == owner_id
    assert audit_entry.data_json["recipient_id"] == recipient_id


@pytest.mark.anyio
async def test_certification_emits_audit(client, admin_headers, db_session):
    account_payload = {"username": f"cert-{uuid4().hex[:8]}", "email": f"cert-{uuid4().hex[:8]}@example.com"}
    account = await client.post("/users", json=account_payload, headers=admin_headers)
    account_id = account.json()["id"]

    response = await client.post(
        "/certified",
        json={"user_id": account_id, "level": "gold"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    audit_entry = (
        db_session.execute(
            select(AuditLog)
            .where(AuditLog.action == "ACCOUNT_CERTIFIED")
            .order_by(AuditLog.at.desc())
        )
        .scalars()
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.data_json["account_id"] == account_id
    assert audit_entry.data_json["level"].upper() == "GOLD"
