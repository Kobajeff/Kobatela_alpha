"""Tests for milestone sequencing and photo metadata validation."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models import Milestone, MilestoneStatus


async def _setup_users_and_escrow(client, auth_headers):
    client_resp = await client.post(
        "/users",
        json={"username": "client-seq", "email": "client-seq@example.com"},
        headers=auth_headers,
    )
    provider_resp = await client.post(
        "/users",
        json={"username": "provider-seq", "email": "provider-seq@example.com"},
        headers=auth_headers,
    )
    assert client_resp.status_code == 201
    assert provider_resp.status_code == 201

    escrow_resp = await client.post(
        "/escrows",
        json={
            "client_id": client_resp.json()["id"],
            "provider_id": provider_resp.json()["id"],
            "amount_total": 1000.0,
            "currency": "USD",
            "release_conditions": {"type": "milestone"},
            "deadline_at": datetime.now(tz=UTC).isoformat(),
        },
        headers=auth_headers,
    )
    assert escrow_resp.status_code == 201
    return escrow_resp.json()["id"]


@pytest.mark.anyio("asyncio")
async def test_sequence_error_blocks_future_milestones(client, auth_headers, db_session):
    escrow_id = await _setup_users_and_escrow(client, auth_headers)

    first = Milestone(
        escrow_id=escrow_id,
        idx=1,
        label="First milestone",
        amount=Decimal("100.00"),
        proof_type="PHOTO",
        validator="SENDER",
    )
    second = Milestone(
        escrow_id=escrow_id,
        idx=2,
        label="Second milestone",
        amount=Decimal("200.00"),
        proof_type="PHOTO",
        validator="SENDER",
    )
    db_session.add_all([first, second])
    db_session.flush()

    resp = await client.post(
        "/proofs",
        json={
            "escrow_id": escrow_id,
            "milestone_idx": 2,
            "type": "PHOTO",
            "storage_url": "https://example.com/proof2.jpg",
            "sha256": "hash-second",
            "metadata": {
                "exif_timestamp": datetime.now(tz=UTC).isoformat(),
                "gps_lat": 5.0,
                "gps_lng": -4.0,
                "source": "camera",
            },
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "SEQUENCE_ERROR"


@pytest.mark.anyio("asyncio")
async def test_photo_outside_geofence_rejected(client, auth_headers, db_session):
    escrow_id = await _setup_users_and_escrow(client, auth_headers)

    milestone = Milestone(
        escrow_id=escrow_id,
        idx=1,
        label="Geofenced milestone",
        amount=Decimal("150.00"),
        proof_type="PHOTO",
        validator="SENDER",
        geofence_lat=5.3210,
        geofence_lng=-4.0123,
        geofence_radius_m=200.0,
    )
    db_session.add(milestone)
    db_session.flush()

    resp = await client.post(
        "/proofs",
        json={
            "escrow_id": escrow_id,
            "milestone_idx": 1,
            "type": "PHOTO",
            "storage_url": "https://example.com/outside.jpg",
            "sha256": "hash-outside",
            "metadata": {
                "exif_timestamp": datetime.now(tz=UTC).isoformat(),
                "gps_lat": 5.3240,
                "gps_lng": -4.0200,
                "source": "camera",
            },
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "GEOFENCE_VIOLATION"


@pytest.mark.anyio("asyncio")
async def test_photo_with_untrusted_source_requires_review(client, auth_headers, db_session):
    escrow_id = await _setup_users_and_escrow(client, auth_headers)

    milestone = Milestone(
        escrow_id=escrow_id,
        idx=1,
        label="Photo milestone",
        amount=Decimal("180.00"),
        proof_type="PHOTO",
        validator="SENDER",
        geofence_lat=5.0,
        geofence_lng=-4.0,
        geofence_radius_m=500.0,
    )
    db_session.add(milestone)
    db_session.flush()

    metadata = {
        "exif_timestamp": (datetime.now(tz=UTC) - timedelta(minutes=30)).isoformat(),
        "gps_lat": 5.0005,
        "gps_lng": -4.0005,
        "source": "unknown",
    }

    resp = await client.post(
        "/proofs",
        json={
            "escrow_id": escrow_id,
            "milestone_idx": 1,
            "type": "PHOTO",
            "storage_url": "https://example.com/proof.jpg",
            "sha256": "hash-review",
            "metadata": metadata,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "PENDING"
    assert body["metadata"]["review_reason"] == "UNTRUSTED_SOURCE"
    assert "review_reasons" in body["metadata"]
    assert "untrusted_source" in body["metadata"]["review_reasons"]

    db_session.refresh(milestone)
    assert milestone.status == MilestoneStatus.PENDING_REVIEW
