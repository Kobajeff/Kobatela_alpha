from app.config import get_settings
from app.services.invoice_ocr import (
    InvoiceOCRResult,
    normalize_ocr_result,
    run_invoice_ocr_if_enabled,
)


def test_run_invoice_ocr_disabled(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "INVOICE_OCR_ENABLED", False, raising=False)

    result = run_invoice_ocr_if_enabled(b"pdf-bytes-go-here")
    validated = InvoiceOCRResult.model_validate(result)
    assert validated.ocr_status == "disabled"
    assert validated.total_amount is None
    assert validated.currency is None


def test_run_invoice_ocr_dummy_provider_validates(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "INVOICE_OCR_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "INVOICE_OCR_PROVIDER", "dummy", raising=False)

    result = run_invoice_ocr_if_enabled(b"pdf-bytes-go-here")
    model = InvoiceOCRResult.model_validate(result)
    assert model.ocr_status in ("disabled", "success", "error")
    assert model.ocr_provider in ("dummy", "disabled", "unknown")


def test_normalize_ocr_result_handles_invalid_payload():
    raw = {
        "ocr_status": 123,
        "total_amount": "not-a-number",
        "currency": "EURO",
    }

    result = normalize_ocr_result(raw)
    assert result["ocr_status"] == "error"
    assert result["total_amount"] is None
    assert result["currency"] is None

