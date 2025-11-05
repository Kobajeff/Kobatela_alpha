from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.anyio("asyncio")
async def test_escrow_happy_path(client, auth_headers):
    client_user = await client.post("/users", json={"username": "client", "email": "client@example.com"}, headers=auth_headers)
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
    escrow_id = escrow_response.json()["id"]

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
