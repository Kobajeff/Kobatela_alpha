"""AI Proof Advisor service for KCT.

This module centralises calls to the OpenAI API to analyse proofs
(invoices, photos, etc.) and return structured risk assessments.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional


from app.config import get_settings
from app.services.ai_proof_flags import ai_enabled, ai_model, ai_timeout_seconds
from app.utils.masking import mask_metadata_for_ai, mask_proof_metadata

try:
    from openai import (  # type: ignore[import-not-found]
        APITimeoutError,
        APIError,
        RateLimitError,
        OpenAI,
    )
except Exception:  # noqa: BLE001
    OpenAI = None
    APIError = None
    RateLimitError = None
    APITimeoutError = None

logger = logging.getLogger(__name__)

_AI_FAILURES = 0
_AI_FAILURE_THRESHOLD = 5
_AI_CIRCUIT_OPEN = False
_AI_CALLS_TOTAL = 0
_AI_ERRORS_TOTAL = 0


def _should_skip_ai() -> bool:
    return _AI_CIRCUIT_OPEN


def _record_ai_failure():
    global _AI_FAILURES, _AI_CIRCUIT_OPEN
    _record_ai_error()
    _AI_FAILURES += 1
    if _AI_FAILURES >= _AI_FAILURE_THRESHOLD:
        _AI_CIRCUIT_OPEN = True


def _record_ai_success():
    global _AI_FAILURES, _AI_CIRCUIT_OPEN, _AI_CALLS_TOTAL
    _AI_CALLS_TOTAL += 1
    _AI_FAILURES = 0
    _AI_CIRCUIT_OPEN = False


def _record_ai_error():
    global _AI_CALLS_TOTAL, _AI_ERRORS_TOTAL
    _AI_CALLS_TOTAL += 1
    _AI_ERRORS_TOTAL += 1


def get_ai_stats() -> Dict[str, int]:
    """Return basic runtime stats for AI Proof Advisor usage."""

    return {
        "calls": _AI_CALLS_TOTAL,
        "errors": _AI_ERRORS_TOTAL,
    }

# --------------------------------------------------
# 1️⃣ Core prompt (cacheable, ne change plus sans versioning)
# --------------------------------------------------
AI_PROOF_ADVISOR_CORE_PROMPT = """
You are “Kobatela AI Proof Advisor v1”, a STRICT risk-analysis assistant for the Kobatela Conditional Transfer (KCT) platform.

Your mission:
- You analyse PROOFS (invoices, payment receipts, delivery photos, project photos, etc.) plus structured JSON context sent by the backend.
- You NEVER approve or reject payments yourself.
- You ONLY provide a structured, machine-readable risk assessment and a short explanation to help a human reviewer.

=== OUTPUT CONTRACT (VERY IMPORTANT) ===

You MUST ALWAYS return a SINGLE valid JSON object and NOTHING ELSE.
No markdown, no comments, no extra text.

The JSON MUST strictly follow this schema:

{
  "risk_level": "clean | warning | suspect",
  "score": 0.0,
  "flags": [],
  "explanation": "..."
}

- "risk_level":
  - "clean"   => Data and content look coherent with the mandate. No strong sign of fraud.
  - "warning" => Some information is missing, ambiguous, or slightly inconsistent. Human review recommended.
  - "suspect" => Strong signs of fraud, manipulation, or incoherence. Human escalation strongly recommended.

- "score":
  - A float between 0.0 and 1.0.
  - Higher = cleaner.
  - Typical ranges:
    - CLEAN   => 0.75 – 1.0 (only if you are genuinely confident).
    - WARNING => 0.40 – 0.80.
    - SUSPECT => 0.0 – 0.45.

- "flags":
  - A list of SHORT, MACHINE-READABLE codes describing the main signals or issues you detected.
  - Use lowercase_with_underscores.
  - Examples (non-exhaustive, you can combine several):
    - "gps_ok"
    - "gps_missing"
    - "gps_far_from_expected"
    - "date_ok"
    - "date_diff_small"
    - "date_diff_large"
    - "duplicate_hash"
    - "invoice_amount_match"
    - "invoice_amount_mismatch_small"
    - "invoice_amount_mismatch_large"
    - "supplier_name_mismatch"
    - "iban_mismatch"
    - "beneficiary_name_mismatch"
    - "image_low_quality"
    - "image_ai_generated_like"
    - "invoice_unreadable"
    - "content_inconsistent_with_mandate"
    - "missing_required_field"
    - "suspicious_layout_or_logo"

- "explanation":
  - A short, human-readable explanation (2 to 8 sentences).
  - It MUST be written in French, in a clear and professional tone.
  - It must summarise:
    - Why you chose this risk_level.
    - Which main issues or signals (flags) influenced your decision.

=== RISK LEVEL POLICY ===

Use the following logic consistently:

1) CLEAN
- The proof looks coherent with the mandate context (amount, currency, supplier, beneficiary, type of expense, dates, location).
- No strong signs of manipulation or fraud.
- Minor imperfections are acceptable (typos, small noise, slight cropping).
- Do NOT use "clean" if there are serious doubts or missing key data.

2) WARNING
- Some information is missing, hard to read, blurred or partially inconsistent.
- Examples:
  - A small difference between expected and actual amount.
  - The date or location is slightly off but still plausible.
  - EXIF/GPS data is missing or incomplete, but nothing clearly impossible.
  - One or two fields look strange but could be a normal variation.
- Human review is recommended before accepting the proof.

3) SUSPECT
- Strong signs of fraud, manipulation, or clear incoherence.
- Examples:
  - The proof is a clear duplicate of a previous one (same hash, same layout, same values but used for a different mandate).
  - GPS/location is impossible or very far from the expected area without explanation.
  - The supplier or beneficiary name / IBAN is clearly different from the mandate context.
  - The image looks very artificial or AI-generated for a context where this is suspicious.
  - The invoice text is incoherent with the project (wrong items, wrong quantities, wrong dates).
- Human escalation is strongly recommended.

=== GENERAL RULES ===

- You always receive:
  - A structured JSON context from the backend (mandate_context, backend_checks, document_context, etc.).
  - Optionally, OCR text and/or an attached image/PDF.
- First, USE the backend checks as signals (e.g. distance, date_diff_days, duplicate hash).
- Second, combine them with the visual/text content to form your global risk assessment.

- Be conservative with "clean" on high-risk patterns.
  - If you see important missing data or weird signals, prefer "warning" or "suspect".
- Do NOT penalise normal privacy or masking:
  - Example: partially masked IBAN or address is acceptable if other elements are coherent.

- If the provided data is too incomplete or unreadable to decide:
  - Prefer "warning" or "suspect" with flags like:
    - "missing_required_field"
    - "invoice_unreadable"
    - "insufficient_data_for_confident_assessment"

=== LANGUAGE AND FORMAT REMINDER ===

- Your EXPLANATION must be in FRENCH.
- The rest (risk_level, flags) must be in English as defined above.
- You MUST ONLY output the JSON object, strictly following the schema:

{
  "risk_level": "clean | warning | suspect",
  "score": 0.0,
  "flags": [],
  "explanation": "..."
}
""".strip()


# --------------------------------------------------
# 2️⃣ Helpers pour construire le message user
# --------------------------------------------------
def build_ai_user_content(
    context: Dict[str, Any],
) -> str:
    """Build the user message content sent to the AI.

    The ``context`` dict should already contain:
    - "mandate_context": mandate / milestone / beneficiary context
    - "backend_checks": backend-computed validations (geofence, dates...)
    - "document_context": information about the uploaded document
    - optionally "ocr_text": OCR-extracted text
    """

    return (
        "Voici les données de contexte et de vérifications backend pour une preuve.\n"
        "Analyse-les selon tes instructions et renvoie STRICTEMENT un JSON conforme au schéma.\n\n"
        f"JSON_CONTEXT:\n{json.dumps(context, ensure_ascii=False)}"
    )


def _normalize_ai_result(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise et sécurise la sortie de l'IA."""

    risk_level = str(raw.get("risk_level", "warning")).lower()
    if risk_level not in {"clean", "warning", "suspect"}:
        risk_level = "warning"

    try:
        score = float(raw.get("score", 0.5))
    except (TypeError, ValueError):
        score = 0.5
    score = max(0.0, min(1.0, score))

    flags = raw.get("flags") or []
    if not isinstance(flags, list):
        flags = [str(flags)]
    flags = [str(f) for f in flags]

    explanation = raw.get("explanation") or ""
    explanation = str(explanation).strip()

    return {
        "risk_level": risk_level,
        "score": score,
        "flags": flags,
        "explanation": explanation,
    }


def _sanitize_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """Return a deep-copied context with sensitive fields masked."""

    try:
        ctx = json.loads(json.dumps(context, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        ctx = {}

    doc = ctx.get("document_context") or {}
    url = doc.get("storage_url")
    if isinstance(url, str):
        doc["storage_url"] = url.rsplit("/", 1)[-1]
    metadata_for_ai = mask_metadata_for_ai(doc.get("metadata"))
    masked_doc = mask_proof_metadata(doc) or {}
    if metadata_for_ai:
        masked_doc["metadata"] = metadata_for_ai
    else:
        masked_doc.pop("metadata", None)
    ctx["document_context"] = masked_doc
    ctx["mandate_context"] = mask_metadata_for_ai(ctx.get("mandate_context") or {})
    ctx["backend_checks"] = mask_metadata_for_ai(ctx.get("backend_checks") or {})
    return ctx


# --------------------------------------------------
# 3️⃣ Fonction principale : appel OpenAI
# --------------------------------------------------
def _fallback_response(*, flags: list[str], explanation: str, score: float = 0.5) -> Dict[str, Any]:
    return {
        "risk_level": "warning",
        "score": score,
        "flags": ["ai_unavailable", *flags],
        "explanation": explanation,
    }


def call_ai_proof_advisor(
    *,
    model: str = "gpt-5.1-mini",
    context: Dict[str, Any],
    proof_storage_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Call the Kobatela AI Proof Advisor."""

    start = time.monotonic()
    status = "success"
    outcome_reason: str | None = None
    settings = get_settings()

    try:
        if _should_skip_ai():
            status = "circuit_breaker_open"
            outcome_reason = "circuit_breaker_open"
            logger.warning("AI circuit breaker open; skipping advisory call.")
            _record_ai_error()
            return {
                "risk_level": "warning",
                "score": 0.5,
                "flags": ["ai_unavailable", "circuit_breaker_open"],
                "explanation": "AI circuit breaker open; skipping advisory.",
            }

        if not ai_enabled():
            status = "disabled"
            outcome_reason = "ai_disabled"
            logger.warning(
                "AI Proof Advisor requested while feature is disabled; returning fallback result."
            )
            _record_ai_error()
            return _fallback_response(
                flags=["ai_disabled"],
                explanation=(
                    "L'analyse automatique n'est pas activée pour cet environnement. "
                    "Merci d'effectuer une revue manuelle."
                ),
            )

        api_key = settings.OPENAI_API_KEY
        if not api_key:
            status = "missing_api_key"
            outcome_reason = "missing_api_key"
            logger.warning("OPENAI_API_KEY is not set; returning fallback AI result.")
            _record_ai_error()
            return _fallback_response(
                flags=["missing_api_key"],
                explanation=(
                    "L'analyse automatique n'a pas pu être effectuée car la clé API n'est pas configurée. "
                    "Une revue manuelle est recommandée."
                ),
            )

        sanitized_context = _sanitize_context(context)
        user_content = build_ai_user_content(sanitized_context)
        if OpenAI is None:
            status = "missing_sdk"
            outcome_reason = "missing_sdk"
            logger.warning("OpenAI SDK is not installed; returning fallback AI result.")
            _record_ai_error()
            return _fallback_response(
                flags=["missing_sdk"],
                explanation=(
                    "L'analyse automatique n'a pas pu être effectuée car le SDK OpenAI n'est pas disponible. "
                    "Merci de vérifier cette preuve manuellement."
                ),
            )

        client = OpenAI(api_key=api_key)

        messages: List[Dict[str, Any]] = []
        messages.append(
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": AI_PROOF_ADVISOR_CORE_PROMPT,
                    }
                ],
            }
        )

        user_content_parts: List[Dict[str, Any]] = [
            {
                "type": "input_text",
                "text": user_content,
            }
        ]

        if proof_storage_url:
            user_content_parts.append(
                {
                    "type": "input_image",
                    "image_url": proof_storage_url,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": user_content_parts,
            }
        )

        resp = client.responses.create(
            model=model or ai_model(),
            input=messages,
            timeout=ai_timeout_seconds(),
        )

        raw_text = getattr(resp, "output_text", None)
        if not raw_text:
            try:
                output_chunks = getattr(resp, "output", []) or []
                parts: List[str] = []
                for chunk in output_chunks:
                    for content_item in getattr(chunk, "content", []) or []:
                        if getattr(content_item, "type", None) == "output_text":
                            parts.append(getattr(content_item, "text", ""))
                raw_text = "".join(parts)
            except Exception:  # noqa: BLE001
                raw_text = None

        if not raw_text:
            raise ValueError("AI Proof Advisor did not return any text output")

        raw_data = json.loads(raw_text)
        result = _normalize_ai_result(raw_data)
        _record_ai_success()
        return result

    except Exception as exc:  # noqa: BLE001
        if RateLimitError and isinstance(exc, RateLimitError):
            status = "rate_limited"
            outcome_reason = "rate_limited"
            logger.warning("AI proof advisor rate limited", extra={"error": str(exc)})
            _record_ai_failure()
            return _fallback_response(
                flags=["rate_limited_or_timeout"],
                score=0.4,
                explanation=(
                    "L'analyse automatique a échoué en raison d'une limite de requêtes ou d'un délai dépassé. "
                    "Une revue manuelle est recommandée."
                ),
            )
        if APITimeoutError and isinstance(exc, APITimeoutError):
            status = "timeout"
            outcome_reason = "timeout"
            logger.warning("AI proof advisor timeout", extra={"error": str(exc)})
            _record_ai_failure()
            return _fallback_response(
                flags=["rate_limited_or_timeout"],
                score=0.4,
                explanation=(
                    "L'analyse automatique a dépassé le délai autorisé. Merci de vérifier cette preuve manuellement."
                ),
            )
        if APIError and isinstance(exc, APIError):
            status = "api_error"
            outcome_reason = "api_error"
            logger.exception("AI proof advisor API error: %s", exc)
            _record_ai_failure()
            return _fallback_response(
                flags=["api_error"],
                score=0.4,
                explanation=(
                    "L'analyse automatique n'a pas pu être effectuée en raison d'une erreur du fournisseur d'IA. "
                    "Merci de procéder à une revue manuelle."
                ),
            )

        status = "error"
        outcome_reason = "exception_during_call"
        logger.exception("AI proof advisor call failed: %s", exc)
        logger.warning(
            "AI proof advisor fallback response emitted",
            extra={"reason": "exception_during_call"},
        )
        _record_ai_failure()
        return _fallback_response(
            flags=["exception_during_call"],
            score=0.4,
            explanation=(
                "L'analyse automatique de la preuve n'a pas pu être réalisée en raison d'une erreur technique. "
                "Merci de vérifier cette preuve manuellement."
            ),
        )
    finally:
        duration = time.monotonic() - start
        logger.info(
            "AI proof advisor call completed",
            extra={
                "status": status,
                "duration_seconds": duration,
                "reason": outcome_reason,
                "proof_storage_url_present": bool(proof_storage_url),
            },
        )
