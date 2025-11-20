import pytest


def test_ai_proof_advisor_logs_status(monkeypatch):
    from app.services import ai_proof_advisor

    monkeypatch.setattr(ai_proof_advisor, "ai_enabled", lambda: False)

    result = ai_proof_advisor.call_ai_proof_advisor(
        context={"document_context": {"metadata": {}}},
        proof_storage_url=None,
    )

    assert result["risk_level"] == "warning"
    assert "ai_disabled" in result.get("flags", [])


def test_invoice_ocr_logs_status(monkeypatch):
    from app.services import invoice_ocr

    class DummySettings:
        INVOICE_OCR_PROVIDER = "none"

    monkeypatch.setattr(invoice_ocr, "_current_settings", lambda: DummySettings())
    monkeypatch.setattr(invoice_ocr, "invoice_ocr_enabled", lambda: False)

    metadata = invoice_ocr.enrich_metadata_with_invoice_ocr(
        storage_url="test://file.pdf", existing_metadata={}
    )

    assert metadata["ocr_status"] == "disabled"
    assert metadata["ocr_provider"] == "none"
