from app.models.audit import AuditLog
from app.utils.audit import log_audit


def test_audit_log_masks_sensitive_fields(db_session):
    payload = {
        "storage_url": "https://files.example.com/proofs/abc123.png?token=secret",
        "iban": "FR7612345678901234567890185",
        "email": "sensitive@example.com",
        "nested": [{"iban_last4": "1234"}],
    }

    log_audit(
        db_session,
        actor="test",
        action="MASK_TEST",
        entity="Proof",
        entity_id=1,
        data=payload,
    )
    db_session.commit()

    entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "MASK_TEST")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert entry is not None
    assert entry.data_json["storage_url"].endswith("/***")
    assert entry.data_json["iban"].startswith("***")
    assert entry.data_json["email"].startswith("***@")
    assert entry.data_json["nested"][0]["iban_last4"].startswith("***")
