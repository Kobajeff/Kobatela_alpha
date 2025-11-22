from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models import EscrowAgreement, EscrowStatus, Milestone, MilestoneStatus, Proof, User
from app.services import proofs as proofs_service
from app.utils.time import utcnow


def _create_flagged_proof(db_session) -> int:
    client = User(username="ai-client", email="ai-client@example.com")
    provider = User(username="ai-provider", email="ai-provider@example.com")
    db_session.add_all([client, provider])
    db_session.flush()

    escrow = EscrowAgreement(
        client_id=client.id,
        provider_id=provider.id,
        amount_total=Decimal("100.00"),
        currency="USD",
        status=EscrowStatus.FUNDED,
        release_conditions_json={},
        deadline_at=utcnow(),
    )
    db_session.add(escrow)
    db_session.flush()

    milestone = Milestone(
        escrow_id=escrow.id,
        idx=1,
        label="AI Review Milestone",
        amount=Decimal("50.00"),
        proof_type="PHOTO",
        validator="SENDER",
        status=MilestoneStatus.PENDING_REVIEW,
    )
    db_session.add(milestone)
    db_session.flush()

    proof = Proof(
        escrow_id=escrow.id,
        milestone_id=milestone.id,
        type="PHOTO",
        storage_url="https://storage/proof.png",
        sha256="hash-ai-review",
        metadata_={},
        status="PENDING",
        created_at=utcnow(),
        ai_risk_level="warning",
    )
    db_session.add(proof)
    db_session.commit()
    return proof.id


def test_decide_proof_requires_note_for_ai_warning(db_session, monkeypatch):
    proof_id = _create_flagged_proof(db_session)

    def fake_approve(db, proof_id, note=None, actor=None):
        proof = db.get(Proof, proof_id)
        proof.status = "APPROVED"
        return proof

    monkeypatch.setattr(proofs_service, "approve_proof", fake_approve)

    with pytest.raises(HTTPException) as exc:
        proofs_service.decide_proof(
            db_session,
            proof_id,
            decision="approved",
            note=None,
            actor="apikey:reviewer",
        )

    assert exc.value.status_code == 400
    assert exc.value.detail["error"]["code"] == "AI_REVIEW_NOTE_REQUIRED"


def test_decide_proof_records_ai_review_metadata(db_session, monkeypatch):
    proof_id = _create_flagged_proof(db_session)

    def fake_approve(db, proof_id, note=None, actor=None):
        proof = db.get(Proof, proof_id)
        proof.status = "APPROVED"
        return proof

    monkeypatch.setattr(proofs_service, "approve_proof", fake_approve)

    result = proofs_service.decide_proof(
        db_session,
        proof_id,
        decision="approved",
        note="Valid despite warning",
        actor="apikey:auditor",
    )

    assert result.ai_reviewed_by == "apikey:auditor"
    assert result.ai_reviewed_at is not None
    assert result.status == "APPROVED"
