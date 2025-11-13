"""Tests for conditional usage spending."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest


@pytest.mark.anyio("asyncio")
async def test_add_payee_and_spend_limits(client, auth_headers):
    buyer = await client.post(
        "/users",
        json={"username": "usage-buyer", "email": "usage-buyer@example.com"},
        headers=auth_headers,
    )
    provider = await client.post(
        "/users",
        json={"username": "usage-provider", "email": "usage-provider@example.com"},
        headers=auth_headers,
    )
    assert buyer.status_code == 201
    assert provider.status_code == 201
    buyer_id = buyer.json()["id"]
    provider_id = provider.json()["id"]

    escrow_resp = await client.post(
        "/escrows",
        json={
            "client_id": buyer_id,
            "provider_id": provider_id,
            "amount_total": 300.0,
            "currency": "USD",
            "release_conditions": {"type": "usage"},
            "deadline_at": datetime.now(tz=UTC).isoformat(),
        },
        headers=auth_headers,
    )
    assert escrow_resp.status_code == 201
    escrow_id = escrow_resp.json()["id"]

    deposit = await client.post(
        f"/escrows/{escrow_id}/deposit",
        json={"amount": 200.0},
        headers={**auth_headers, "Idempotency-Key": "usage-dep-1"},
    )
    assert deposit.status_code == 200

    allow_daily = await client.post(
        "/spend/allowed",
        json={
            "escrow_id": escrow_id,
            "payee_ref": "IBAN-XYZ-001",
            "label": "Trusted Clinic",
            "daily_limit": 120.0,
            "total_limit": 400.0,
        },
        headers=auth_headers,
    )
    assert allow_daily.status_code == 201

    spend_ok = await client.post(
        "/spend",
        json={"escrow_id": escrow_id, "payee_ref": "IBAN-XYZ-001", "amount": 90.0},
        headers={**auth_headers, "Idempotency-Key": "usage-spend-1"},
    )
    assert spend_ok.status_code == 200
    spend_payload = spend_ok.json()
    assert spend_payload["status"] == "SENT"

    idempotent = await client.post(
        "/spend",
        json={"escrow_id": escrow_id, "payee_ref": "IBAN-XYZ-001", "amount": 90.0},
        headers={**auth_headers, "Idempotency-Key": "usage-spend-1"},
    )
    assert idempotent.status_code == 200
    assert idempotent.json()["payment_id"] == spend_payload["payment_id"]

    exceed_daily = await client.post(
        "/spend",
        json={"escrow_id": escrow_id, "payee_ref": "IBAN-XYZ-001", "amount": 40.0},
        headers={**auth_headers, "Idempotency-Key": f"usage-spend-{uuid4().hex}"},
    )
    assert exceed_daily.status_code == 409
    assert exceed_daily.json()["error"]["code"] == "DAILY_LIMIT_REACHED"

    allow_total = await client.post(
        "/spend/allowed",
        json={
            "escrow_id": escrow_id,
            "payee_ref": "IBAN-XYZ-002",
            "label": "Partner Supplier",
            "daily_limit": 500.0,
            "total_limit": 150.0,
        },
        headers=auth_headers,
    )
    assert allow_total.status_code == 201

    total_spend_ok = await client.post(
        "/spend",
        json={"escrow_id": escrow_id, "payee_ref": "IBAN-XYZ-002", "amount": 100.0},
        headers={**auth_headers, "Idempotency-Key": "usage-spend-2"},
    )
    assert total_spend_ok.status_code == 200

    exceed_total = await client.post(
        "/spend",
        json={"escrow_id": escrow_id, "payee_ref": "IBAN-XYZ-002", "amount": 60.0},
        headers={**auth_headers, "Idempotency-Key": f"usage-spend-{uuid4().hex}"},
    )
    assert exceed_total.status_code == 409
    assert exceed_total.json()["error"]["code"] == "TOTAL_LIMIT_REACHED"
