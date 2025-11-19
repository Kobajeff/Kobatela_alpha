from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.audit import AuditLog
from app.models.escrow import EscrowDeposit
from app.models.user import User
from app.schemas.escrow import EscrowActionPayload, EscrowCreate, EscrowDepositCreate
from app.services import escrow as escrow_service
from app.utils.time import utcnow


async def _create_basic_escrow(client, auth_headers) -> int:
    client_user = await client.post(
        "/users", json={"username": "client", "email": "client@example.com"}, headers=auth_headers
    )
    provider_user = await client.post(
        "/users", json={"username": "provider", "email": "provider@example.com"}, headers=auth_headers
    )
    deadline = (datetime.now(tz=timezone.utc) + timedelta(days=2)).isoformat()
    escrow_response = await client.post(
        "/escrows",
        json={
            "client_id": client_user.json()["id"],
            "provider_id": provider_user.json()["id"],
            "amount_total": 500.0,
            "currency": "USD",
            "release_conditions": {"proof": "delivery"},
            "deadline_at": deadline,
        },
        headers=auth_headers,
    )
    assert escrow_response.status_code == 201
    return escrow_response.json()["id"]


@pytest.mark.anyio("asyncio")
async def test_escrow_happy_path(client, auth_headers):
    escrow_id = await _create_basic_escrow(client, auth_headers)

    deposit_headers = {**auth_headers, "Idempotency-Key": "deposit-key"}
    deposit = await client.post(
        f"/escrows/{escrow_id}/deposit",
        json={"amount": 500.0},
        headers=deposit_headers,
    )
    assert deposit.status_code == 200
    assert deposit.json()["status"] == "FUNDED"

    # Retry deposit idempotently
    retry = await client.post(
        f"/escrows/{escrow_id}/deposit",
        json={"amount": 500.0},
        headers=deposit_headers,
    )
    assert retry.status_code == 200
    assert retry.json()["status"] == "FUNDED"

    delivered = await client.post(
        f"/escrows/{escrow_id}/mark-delivered",
        json={"note": "proof uploaded", "proof_url": "http://example.com/proof"},
        headers=auth_headers,
    )
    assert delivered.status_code == 200
    assert delivered.json()["status"] == "RELEASABLE"

    approved = await client.post(
        f"/escrows/{escrow_id}/client-approve",
        json={"note": "looks good"},
        headers=auth_headers,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "RELEASED"

    fetched = await client.get(f"/escrows/{escrow_id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "RELEASED"


def test_escrow_state_changes_emit_audit_logs(db_session):
    """Every escrow transition should be audit logged."""

    client = User(username="escrow-client", email="escrow-client@example.com")
    provider = User(username="escrow-provider", email="escrow-provider@example.com")
    db_session.add_all([client, provider])
    db_session.flush()

    escrow = escrow_service.create_escrow(
        db_session,
        EscrowCreate(
            client_id=client.id,
            provider_id=provider.id,
            amount_total=Decimal("100.00"),
            currency="USD",
            release_conditions={},
            deadline_at=utcnow() + timedelta(days=5),
        ),
    )

    escrow_service.deposit(
        db_session,
        escrow.id,
        EscrowDepositCreate(amount=Decimal("100.00")),
        idempotency_key="audit-deposit",
    )

    escrow_service.mark_delivered(
        db_session,
        escrow.id,
        EscrowActionPayload(note="proof", proof_url="https://example.com/proof"),
    )

    escrow_service.client_approve(
        db_session,
        escrow.id,
        EscrowActionPayload(note="looks good", proof_url=None),
    )

    actions = [log.action for log in db_session.query(AuditLog).order_by(AuditLog.id).all()]
    assert actions == [
        "ESCROW_CREATED",
        "ESCROW_DEPOSITED",
        "ESCROW_PROOF_UPLOADED",
        "ESCROW_RELEASED",
    ]


@pytest.mark.anyio("asyncio")
async def test_deposit_requires_idempotency_key(client, auth_headers):
    escrow_id = await _create_basic_escrow(client, auth_headers)

    response = await client.post(f"/escrows/{escrow_id}/deposit", json={"amount": 100.0}, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.anyio("asyncio")
async def test_deposit_rejects_blank_idempotency_key(client, auth_headers):
    escrow_id = await _create_basic_escrow(client, auth_headers)

    response = await client.post(
        f"/escrows/{escrow_id}/deposit",
        json={"amount": 100.0},
        headers={**auth_headers, "Idempotency-Key": "   "},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


@pytest.mark.anyio("asyncio")
async def test_deposit_idempotent_key_creates_single_row(client, auth_headers, db_session):
    escrow_id = await _create_basic_escrow(client, auth_headers)
    headers = {**auth_headers, "Idempotency-Key": "escrow-deposit-test"}

    first = await client.post(f"/escrows/{escrow_id}/deposit", json={"amount": 50}, headers=headers)
    assert first.status_code == 200

    retry = await client.post(f"/escrows/{escrow_id}/deposit", json={"amount": 50}, headers=headers)
    assert retry.status_code == 200

    deposits = db_session.query(EscrowDeposit).filter(EscrowDeposit.escrow_id == escrow_id).all()
    assert len(deposits) == 1
    assert deposits[0].idempotency_key == "escrow-deposit-test"


@pytest.mark.anyio("asyncio")
async def test_get_escrow_requires_auth(client, auth_headers):
    escrow_id = await _create_basic_escrow(client, auth_headers)

    response = await client.get(f"/escrows/{escrow_id}")
    assert response.status_code == 401


@pytest.mark.anyio("asyncio")
async def test_get_escrow_audits_reads(client, auth_headers, db_session):
    escrow_id = await _create_basic_escrow(client, auth_headers)

    response = await client.get(f"/escrows/{escrow_id}", headers=auth_headers)
    assert response.status_code == 200

    audits = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "ESCROW_READ", AuditLog.entity_id == escrow_id)
        .all()
    )
    assert len(audits) == 1
