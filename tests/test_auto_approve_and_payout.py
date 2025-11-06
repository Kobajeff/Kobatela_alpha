"""Tests covering auto-approval and payout idempotency flows."""
from datetime import UTC, datetime, timedelta
<<<<<<< HEAD
from decimal import Decimal
=======
>>>>>>> origin/main

import pytest
from sqlalchemy import select

from app.models import (
    EscrowAgreement,
    EscrowStatus,
    Milestone,
    MilestoneStatus,
    Payment,
    PaymentStatus,
)
from app.services import milestones as milestones_service
from app.services import payments as payments_service


async def _create_users_and_escrow(client, auth_headers):
    client_resp = await client.post(
        "/users",
        json={"username": "auto-client", "email": "auto-client@example.com"},
        headers=auth_headers,
    )
    provider_resp = await client.post(
        "/users",
        json={"username": "auto-provider", "email": "auto-provider@example.com"},
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


async def _fund_escrow(client, escrow_id: int, amount: float, auth_headers, key: str) -> None:
    fund_resp = await client.post(
        f"/escrows/{escrow_id}/deposit",
        json={"amount": amount},
        headers={**auth_headers, "Idempotency-Key": key},
    )
    assert fund_resp.status_code == 200


@pytest.mark.anyio("asyncio")
async def test_auto_approve_photo_triggers_payout(client, auth_headers, db_session):
    escrow_id = await _create_users_and_escrow(client, auth_headers)

    milestone = Milestone(
        escrow_id=escrow_id,
        idx=1,
        label="Design delivery",
<<<<<<< HEAD
        amount=Decimal("250.00"),
=======
        amount=250.0,
>>>>>>> origin/main
        proof_type="PHOTO",
        validator="SENDER",
        geofence_lat=5.3210,
        geofence_lng=-4.0123,
        geofence_radius_m=400.0,
    )
    db_session.add(milestone)
    db_session.flush()

    await _fund_escrow(client, escrow_id, 250.0, auth_headers, "auto-pay-1")

    metadata = {
        "exif_timestamp": datetime.now(tz=UTC).isoformat(),
        "gps_lat": 5.3211,
        "gps_lng": -4.0122,
        "source": "app",
    }

    proof_resp = await client.post(
        "/proofs",
        json={
            "escrow_id": escrow_id,
            "milestone_idx": 1,
            "type": "PHOTO",
            "storage_url": "https://example.com/clean-proof.jpg",
            "sha256": "hash-clean",
            "metadata": metadata,
        },
        headers=auth_headers,
    )
    assert proof_resp.status_code == 201
    body = proof_resp.json()
    assert body["status"] == "APPROVED"

    db_session.refresh(milestone)
    assert milestone.status == MilestoneStatus.PAID

    payment = db_session.scalars(select(Payment).where(Payment.milestone_id == milestone.id)).one()
    assert payment.status == PaymentStatus.SENT
<<<<<<< HEAD
    assert payment.amount == milestone.amount
=======
    assert payment.amount == pytest.approx(milestone.amount)
>>>>>>> origin/main

    escrow = db_session.get(EscrowAgreement, escrow_id)
    db_session.refresh(escrow)
    assert escrow.status == EscrowStatus.RELEASED
    assert milestones_service.open_next_waiting_milestone(db_session, escrow_id) is None


@pytest.mark.anyio("asyncio")
async def test_payout_idempotency_reuses_payment(client, auth_headers, db_session):
    escrow_id = await _create_users_and_escrow(client, auth_headers)

    milestone = Milestone(
        escrow_id=escrow_id,
        idx=1,
        label="Implementation delivery",
<<<<<<< HEAD
        amount=Decimal("300.00"),
=======
        amount=300.0,
>>>>>>> origin/main
        proof_type="PHOTO",
        validator="SENDER",
        geofence_lat=5.0,
        geofence_lng=-4.0,
        geofence_radius_m=500.0,
    )
    db_session.add(milestone)
    db_session.flush()

    await _fund_escrow(client, escrow_id, 300.0, auth_headers, "auto-pay-2")

    metadata = {
        "exif_timestamp": datetime.now(tz=UTC).isoformat(),
        "gps_lat": 5.0001,
        "gps_lng": -4.0001,
        "source": "app",
    }

    proof_resp = await client.post(
        "/proofs",
        json={
            "escrow_id": escrow_id,
            "milestone_idx": 1,
            "type": "PHOTO",
            "storage_url": "https://example.com/proof-idem.jpg",
            "sha256": "hash-idem",
            "metadata": metadata,
        },
        headers=auth_headers,
    )
    assert proof_resp.status_code == 201

    payment = db_session.scalars(select(Payment).where(Payment.milestone_id == milestone.id)).one()
    escrow = db_session.get(EscrowAgreement, escrow_id)
    db_session.refresh(escrow)

    reused = payments_service.execute_payout(
        db_session,
        escrow=escrow,
        milestone=milestone,
        amount=milestone.amount,
        idempotency_key=f"pay|escrow:{escrow.id}|ms:{milestone.id}|amt:{milestone.amount}",
    )
    assert reused.id == payment.id
    assert reused.status == PaymentStatus.SENT


@pytest.mark.anyio("asyncio")
<<<<<<< HEAD
async def test_execute_payout_rejects_error_reuse(client, auth_headers, db_session):
    escrow_id = await _create_users_and_escrow(client, auth_headers)

    milestone = Milestone(
        escrow_id=escrow_id,
        idx=1,
        label="Error reuse",
        amount=Decimal("150.00"),
        proof_type="PHOTO",
        validator="SENDER",
        geofence_lat=5.0,
        geofence_lng=-4.0,
        geofence_radius_m=500.0,
        status=MilestoneStatus.APPROVED,
    )
    db_session.add(milestone)
    db_session.flush()

    await _fund_escrow(client, escrow_id, 200.0, auth_headers, "auto-pay-error")

    error_payment = Payment(
        escrow_id=escrow_id,
        milestone_id=milestone.id,
        amount=milestone.amount,
        status=PaymentStatus.ERROR,
        idempotency_key="reuse-error",
        psp_ref="PSP-error",
    )
    db_session.add(error_payment)
    db_session.commit()

    escrow = db_session.get(EscrowAgreement, escrow_id)
    db_session.refresh(milestone)

    with pytest.raises(ValueError, match="Existing payment is in ERROR"):
        payments_service.execute_payout(
            db_session,
            escrow=escrow,
            milestone=milestone,
            amount=milestone.amount,
            idempotency_key="reuse-error",
        )


@pytest.mark.anyio("asyncio")
=======
>>>>>>> origin/main
async def test_three_milestones_chain_auto_and_manual(client, auth_headers, db_session):
    escrow_id = await _create_users_and_escrow(client, auth_headers)

    milestones = [
        Milestone(
            escrow_id=escrow_id,
            idx=1,
            label="Kickoff",
<<<<<<< HEAD
            amount=Decimal("120.00"),
=======
            amount=120.0,
>>>>>>> origin/main
            proof_type="PHOTO",
            validator="SENDER",
            geofence_lat=5.1,
            geofence_lng=-4.1,
            geofence_radius_m=300.0,
        ),
        Milestone(
            escrow_id=escrow_id,
            idx=2,
            label="Development",
<<<<<<< HEAD
            amount=Decimal("180.00"),
=======
            amount=180.0,
>>>>>>> origin/main
            proof_type="PHOTO",
            validator="SENDER",
            geofence_lat=5.1,
            geofence_lng=-4.1,
            geofence_radius_m=300.0,
        ),
        Milestone(
            escrow_id=escrow_id,
            idx=3,
            label="Launch",
<<<<<<< HEAD
            amount=Decimal("200.00"),
=======
            amount=200.0,
>>>>>>> origin/main
            proof_type="PHOTO",
            validator="SENDER",
            geofence_lat=5.1,
            geofence_lng=-4.1,
            geofence_radius_m=300.0,
        ),
    ]
    db_session.add_all(milestones)
    db_session.flush()

    await _fund_escrow(client, escrow_id, 500.0, auth_headers, "auto-pay-chain")

    clean_metadata = {
        "exif_timestamp": datetime.now(tz=UTC).isoformat(),
        "gps_lat": 5.1001,
        "gps_lng": -4.0999,
        "source": "app",
    }

    # Milestone 1 auto-approves and pays
    proof1 = await client.post(
        "/proofs",
        json={
            "escrow_id": escrow_id,
            "milestone_idx": 1,
            "type": "PHOTO",
            "storage_url": "https://example.com/proof-1.jpg",
            "sha256": "hash-1",
            "metadata": clean_metadata,
        },
        headers=auth_headers,
    )
    assert proof1.status_code == 201
    db_session.refresh(milestones[0])
    assert milestones[0].status == MilestoneStatus.PAID

    # Milestone 2 suspicious metadata -> review
    suspicious_metadata = {
        "exif_timestamp": (datetime.now(tz=UTC) - timedelta(minutes=20)).isoformat(),
        "gps_lat": 5.1002,
        "gps_lng": -4.0998,
        "source": "unknown",
    }
    proof2 = await client.post(
        "/proofs",
        json={
            "escrow_id": escrow_id,
            "milestone_idx": 2,
            "type": "PHOTO",
            "storage_url": "https://example.com/proof-2.jpg",
            "sha256": "hash-2",
            "metadata": suspicious_metadata,
        },
        headers=auth_headers,
    )
    assert proof2.status_code == 201
    assert proof2.json()["status"] == "PENDING"
    db_session.refresh(milestones[1])
    assert milestones[1].status == MilestoneStatus.PENDING_REVIEW

    decision = await client.post(
        f"/proofs/{proof2.json()['id']}/decision",
        json={"decision": "approved"},
        headers=auth_headers,
    )
    assert decision.status_code == 200
    db_session.refresh(milestones[1])
    assert milestones[1].status == MilestoneStatus.PAID

    # Milestone 3 clean metadata -> auto approve
    proof3 = await client.post(
        "/proofs",
        json={
            "escrow_id": escrow_id,
            "milestone_idx": 3,
            "type": "PHOTO",
            "storage_url": "https://example.com/proof-3.jpg",
            "sha256": "hash-3",
            "metadata": clean_metadata,
        },
        headers=auth_headers,
    )
    assert proof3.status_code == 201
    db_session.refresh(milestones[2])
    assert milestones[2].status == MilestoneStatus.PAID

    escrow = db_session.get(EscrowAgreement, escrow_id)
    db_session.refresh(escrow)
    assert escrow.status == EscrowStatus.RELEASED

    payments = db_session.scalars(select(Payment).where(Payment.escrow_id == escrow_id)).all()
    assert len(payments) == 3
    assert all(payment.status == PaymentStatus.SENT for payment in payments)
