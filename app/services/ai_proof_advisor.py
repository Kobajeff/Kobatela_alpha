"""AI Proof Advisor service for KCT.

This module centralises calls to the OpenAI API to analyse proofs
(invoices, photos, etc.) and return structured risk assessments.
"""
from __future__ import annotations

import json
import logging
import time
from copy import deepcopy
from typing import Any, Dict, List, Optional


from app.config import get_settings
from app.services.ai_proof_flags import ai_enabled, ai_model, ai_timeout_seconds
from app.utils.masking import (
    AI_MASK_PLACEHOLDER,
    SENSITIVE_PATTERNS,
    mask_metadata_for_ai,
)

# Simple in-memory circuit breaker + metrics for AI Proof Advisor
_AI_FAILURE_COUNT: int = 0
_AI_FAILURE_THRESHOLD: int = 5
_AI_CIRCUIT_OPEN: bool = False

_AI_CALLS: int = 0
_AI_ERRORS: int = 0

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


def _record_ai_success() -> None:
    global _AI_FAILURE_COUNT, _AI_CIRCUIT_OPEN
    _AI_FAILURE_COUNT = 0
    _AI_CIRCUIT_OPEN = False


def _record_ai_failure() -> None:
    global _AI_FAILURE_COUNT, _AI_CIRCUIT_OPEN, _AI_ERRORS
    _AI_FAILURE_COUNT += 1
    _AI_ERRORS += 1
    if _AI_FAILURE_COUNT >= _AI_FAILURE_THRESHOLD:
        _AI_CIRCUIT_OPEN = True


def _is_circuit_open() -> bool:
    return _AI_CIRCUIT_OPEN


def _fallback_ai_result(reason: str) -> dict[str, Any]:
    """
    Fallback safe result when AI is unavailable or circuit is open.
    """

    return {
        "risk_level": "warning",
        "score": 0.5,
        "flags": ["ai_unavailable", reason],
        "explanation": (
            "L'analyse automatique de la preuve n'a pas pu être réalisée "
            "en raison d'une indisponibilité temporaire du service d'IA "
            f"({reason}). Merci de vérifier cette preuve manuellement."
        ),
    }


def get_ai_stats() -> dict[str, int]:
    """
    Expose basic counters for health/observability.
    """

    return {
        "calls": _AI_CALLS,
        "errors": _AI_ERRORS,
        "failure_count": _AI_FAILURE_COUNT,
        "circuit_open": int(_AI_CIRCUIT_OPEN),
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


def _mask_sensitive_only(data: dict[str, Any]) -> dict[str, Any]:
    """Mask sensitive keys but keep non-sensitive fields intact."""

    if not isinstance(data, dict):
        return {}

    cleaned: dict[str, Any] = {}
    redacted_keys: list[str] = []

    for key, value in data.items():
        key_lower = str(key).lower()

        if any(pattern in key_lower for pattern in SENSITIVE_PATTERNS):
            cleaned[key] = AI_MASK_PLACEHOLDER
            redacted_keys.append(key)
        else:
            cleaned[key] = value

    if redacted_keys:
        cleaned["_ai_redacted_keys"] = redacted_keys

    return cleaned


def _sanitize_context(context: dict) -> dict:
    """
    Ensure FULL privacy:
    - mask mandate_context
    - mask backend_checks
    - mask document_context.metadata
    """
    if not isinstance(context, dict):
        return {}

    cleaned_context = deepcopy(context)

    # Mandate context – keep non-sensitive signals, redact only sensitive keys
    mandate = cleaned_context.get("mandate_context", {}) or {}
    mandate = mandate if isinstance(mandate, dict) else {}
    cleaned_context["mandate_context"] = _mask_sensitive_only(mandate)

    # Backend checks – keep computed signals, redact only sensitive keys
    backend = cleaned_context.get("backend_checks", {}) or {}
    backend = backend if isinstance(backend, dict) else {}
    cleaned_context["backend_checks"] = _mask_sensitive_only(backend)

    # Document context
    doc_ctx = cleaned_context.get("document_context", {}) or {}
    doc_ctx = doc_ctx if isinstance(doc_ctx, dict) else {}
    doc_meta = doc_ctx.get("metadata", {}) or {}

    cleaned_context["document_context"] = {
        **doc_ctx,
        "metadata": mask_metadata_for_ai(doc_meta),
    }

    return cleaned_context


# --------------------------------------------------
# 3️⃣ Fonction principale : appel OpenAI
# --------------------------------------------------
def _call_ai_proof_once(
    client,
    model: str,
    system_prompt: str,
    sanitized_context: dict[str, Any],
    timeout_seconds: int,
    proof_storage_url: str | None = None,
) -> dict[str, Any]:
    """
    Single low-level call to the AI provider.

    This function assumes:
    - client is already configured OpenAI client (or equivalent),
    - sanitized_context has already been filtered for privacy.
    """

    user_content = build_ai_user_content(sanitized_context)

    messages: List[Dict[str, Any]] = []
    messages.append(
        {
            "role": "system",
            "content": [
                {
                    "type": "input_text",
                    "text": system_prompt,
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
        model=model,
        input=messages,
        timeout=timeout_seconds,
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
    return _normalize_ai_result(raw_data)


def call_ai_proof_advisor(
    *,
    model: str | None = "gpt-5.1-mini",
    context: Dict[str, Any],
    proof_storage_url: Optional[str] = None,
    client: Any | None = None,
    timeout_seconds: int | None = None,
    system_prompt: str | None = None,
) -> Dict[str, Any]:
    """Call the Kobatela AI Proof Advisor with resilience helpers."""

    global _AI_CALLS, _AI_ERRORS

    start = time.monotonic()
    status = "success"
    outcome_reason: str | None = None
    settings = get_settings()

    try:
        if _is_circuit_open():
            status = "circuit_breaker_open"
            outcome_reason = "circuit_breaker_open"
            logger.warning("AI circuit breaker open; skipping advisory call.")
            return _fallback_ai_result("circuit_breaker_open")

        _AI_CALLS += 1

        sanitized_context = _sanitize_context(context)

        if not ai_enabled():
            status = "disabled"
            outcome_reason = "ai_disabled"
            logger.warning(
                "AI Proof Advisor requested while feature is disabled; returning fallback result."
            )
            _AI_ERRORS += 1
            return _fallback_ai_result("ai_disabled")

        api_key = settings.OPENAI_API_KEY
        if not api_key:
            status = "missing_api_key"
            outcome_reason = "missing_api_key"
            logger.warning("OPENAI_API_KEY is not set; returning fallback AI result.")
            _AI_ERRORS += 1
            return _fallback_ai_result("missing_api_key")

        if OpenAI is None:
            status = "missing_sdk"
            outcome_reason = "missing_sdk"
            logger.warning("OpenAI SDK is not installed; returning fallback AI result.")
            _AI_ERRORS += 1
            return _fallback_ai_result("missing_sdk")

        ai_client = client or OpenAI(api_key=api_key)
        model_to_use = model or ai_model()
        timeout_to_use = timeout_seconds or ai_timeout_seconds()
        system_prompt_to_use = system_prompt or AI_PROOF_ADVISOR_CORE_PROMPT

        last_exc: Exception | None = None
        for _attempt in range(2):
            try:
                result = _call_ai_proof_once(
                    client=ai_client,
                    model=model_to_use,
                    system_prompt=system_prompt_to_use,
                    sanitized_context=sanitized_context,
                    timeout_seconds=timeout_to_use,
                    proof_storage_url=proof_storage_url,
                )
                _record_ai_success()
                return result
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                _record_ai_failure()

        status = "error"
        outcome_reason = "retries_exhausted"
        logger.exception("AI Proof Advisor failed after retries: %s", last_exc)
        return _fallback_ai_result("retries_exhausted")
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
