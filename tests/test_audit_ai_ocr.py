import pytest
from decimal import Decimal

from app.models import AuditLog, EscrowAgreement, EscrowStatus, Milestone, MilestoneStatus, Proof, User
from app.schemas.proof import ProofCreate
from app.services import proofs as proofs_service
from app.utils.time import utcnow


def _create_pdf_milestone(db_session):
    client = User(username="audit-client", email="audit-client@example.com")
    provider = User(username="audit-provider", email="audit-provider@example.com")
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
        label="Doc",
        amount=Decimal("100.00"),
        proof_type="PDF",
        validator="SENDER",
        status=MilestoneStatus.WAITING,
    )
    db_session.add(milestone)
    db_session.commit()

    return escrow, milestone


@pytest.mark.anyio("asyncio")
async def test_ai_and_ocr_audit_logs(monkeypatch, db_session):
    escrow, milestone = _create_pdf_milestone(db_session)

    monkeypatch.setattr(proofs_service, "ai_enabled", lambda: True)
    monkeypatch.setattr(
        proofs_service,
        "call_ai_proof_advisor",
        lambda **kwargs: {
            "risk_level": "warning",
            "score": 0.4,
            "flags": ["ai_test"],
            "explanation": "stub",
        },
    )
    monkeypatch.setattr(
        proofs_service,
        "enrich_metadata_with_invoice_ocr",
        lambda storage_url, existing_metadata: {"ocr_status": "success", "ocr_provider": "stub", **(existing_metadata or {})},
    )

    payload = ProofCreate(
        escrow_id=escrow.id,
        milestone_idx=1,
        type="PDF",
        storage_url="https://storage.example.com/proofs/doc.pdf",
        sha256="hash-audit-proof",
        metadata={"invoice_total_amount": "100.00", "invoice_currency": "usd"},
    )

    proof: Proof = proofs_service.submit_proof(db_session, payload, actor="tester")
    db_session.refresh(proof)

    logs = (
        db_session.query(AuditLog)
        .filter(AuditLog.entity == "Proof", AuditLog.entity_id == proof.id)
        .all()
    )

    actions = {log.action for log in logs}
    assert "AI_PROOF_ASSESSMENT" in actions
    assert "INVOICE_OCR_RUN" in actions

    ai_logs = [log for log in logs if log.action == "AI_PROOF_ASSESSMENT"]
    assert ai_logs
    ai_data = ai_logs[0].data_json
    assert ai_data.get("risk_level") == "warning"
    assert ai_data.get("flags") == ["ai_test"]
