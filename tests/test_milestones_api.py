import pytest


@pytest.mark.anyio
async def test_create_and_list_milestones(client, sender_headers, admin_headers, db_session):
    client_user = await client.post(
        "/users",
        headers=admin_headers,
        json={"username": "client-milestone", "email": "client-milestone@example.com"},
    )
    client_user.raise_for_status()
    client_id = client_user.json()["id"]

    provider_user = await client.post(
        "/users",
        headers=admin_headers,
        json={"username": "provider-milestone", "email": "provider-milestone@example.com"},
    )
    provider_user.raise_for_status()
    provider_id = provider_user.json()["id"]

    escrow_response = await client.post(
        "/escrows",
        headers=sender_headers,
        json={
            "client_id": client_id,
            "provider_id": provider_id,
            "amount_total": "100.00",
            "currency": "USD",
            "release_conditions": {"proof": "delivery"},
            "deadline_at": "2030-01-01T00:00:00Z",
        },
    )
    escrow_response.raise_for_status()
    escrow_id = escrow_response.json()["id"]

    milestone_response = await client.post(
        f"/escrows/{escrow_id}/milestones",
        headers=admin_headers,
        json={
            "label": "Phase 1",
            "amount": "100.00",
            "currency": "USD",
            "sequence_index": 1,
            "proof_kind": "PHOTO",
            "proof_requirements": {},
        },
    )
    milestone_response.raise_for_status()
    milestone = milestone_response.json()
    assert milestone["sequence_index"] == 1
    assert milestone["amount"] == "100.00"

    list_response = await client.get(
        f"/escrows/{escrow_id}/milestones",
        headers=sender_headers,
    )
    list_response.raise_for_status()
    data = list_response.json()
    assert len(data) == 1
    assert data[0]["label"] == "Phase 1"
