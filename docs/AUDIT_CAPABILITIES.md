# Kobatela_alpha — Capability & Stability Audit (2025-11-19)

## A. Executive summary
Hardened API-key–based access control on every critical router (escrow, proofs, spend, transactions) and consistent actor propagation into AuditLog, enabling reliable forensics (app/routers/*, app/services/*, app/utils/audit.py).

Proof ingestion pipeline layers EXIF/geofence checks, optional invoice OCR enrichment, structured backend checks, and the AI Proof Advisor with sanitized contexts plus persisted ai_* verdicts (app/services/proofs.py, invoice_ocr.py, document_checks.py, ai_proof_advisor.py).

Monetary flows rely on Numeric columns and _to_decimal normalization so usage mandates, purchases, and escrow payouts stay in lockstep (app/models/*, app/services/spend.py).

PSP webhook security now includes HMAC verification with timestamp drift and dual-secret rotation guards, keeping settlements authoritative (app/services/psp_webhooks.py, app/config.py).

Observability-ready: structured logging, centralized error handlers, Alembic migrations up to 1b7cc2cfcc6e, and a living audit report checked into docs/AUDIT_CAPABILITIES.md.

Legacy clients must now supply Idempotency-Key on /spend/purchases; without rollout comms the stricter guard can block legitimate retries (R1).

PSP secret rotation still manual: even though the code accepts a NEXT secret, there is no operational procedure or alerting when both secrets are unset or stale (R2).

Audit sanitization masks obvious PII but leaves secondary attributes (city, merchant labels) untouched; leaked logs may still reveal personal data (R3).

Misconfigured ALLOW_DB_CREATE_ALL outside dev could still run create_all() despite new guardrails, risking schema drift vs Alembic (R4).

AI override governance depends on reviewers adding notes; no dashboard enforces secondary validation when ai_risk_level in {warning,suspect}, so risk acceptance may be under-documented (R5).

Readiness score: 92 / 100 (GO for a limited staging with ≈10 external users once P0 items are operationalized).

## B. Capability map (current features)
### B.1 Functional coverage
| Feature | Endpoints / modules involved | Status (OK / Partial / Missing) | Notes |
| --- | --- | --- | --- |
| Health & monitoring | GET /health, logging middleware | OK | Lightweight status JSON for uptime probes. |
| User & API key management | app/routers/users.py, app/routers/apikeys.py, app/services/users.py | OK | Create/list users & keys, audit actor recorded. |
| Escrow lifecycle | app/routers/escrow.py, app/services/escrow.py, payments.py | OK | Create, deposit (idempotent), deliver, approve/reject with AuditLog + payouts. |
| Usage mandates & spend | app/routers/spend.py, app/services/spend.py, usage.py | OK | Allow merchants, enforce Decimal normalization, mandatory Idempotency-Key for purchases. |
| Transactions / allowlist | app/routers/transactions.py, allowlist.py, certified.py | OK | Admin-only flows with idempotence & audit. |
| Proof submission & decisions | app/routers/proofs.py, app/services/proofs.py | OK | Photo validations + auto-pay, doc proofs manual review with AI advisory and reviewer notes. |
| PSP webhook & payouts | app/routers/psp.py, app/services/psp_webhooks.py, payments.py | OK | HMAC + timestamp drift, dual-secret rotation, payment status updates. |
| AI Proof Advisor | ai_proof_flags.py, ai_proof_advisor.py, document_checks.py | OK | Flags off by default, sanitized context, persisted AI verdicts. |
| Invoice OCR | app/services/invoice_ocr.py, proof submit hook | Partial | Stub provider; enrichment runs only when flag enabled, no real OCR yet. |

### B.2 End-to-end journeys supported today
- Simple escrow with photo proof: /escrows → /escrows/{id}/deposit → /proofs (PHOTO) → auto-approve via EXIF+geofence → /payments/execute triggered automatically.

- Multi-milestone invoice mandate: /mandates → /spend/allow → /proofs (PDF/INVOICE) with OCR enrichment + AI advisory → manual decision with ai_reviewed_* metadata.

- Merchant purchase flow: /spend/purchases with Idempotency-Key → spend recorded against mandate → AuditLog entry for the actor.

- Admin transaction / allowlist: /allowlist + /certified + /transactions enforcing double checks and idempotence.

- PSP settlement: PSP POST /psp/webhook signed with current or next secret → payments.update_status + AuditLog per event.

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request model | Response model | HTTP codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | /health | routers.health.healthcheck | None | - | - | {status:str} | 200 |
| POST | /users | routers.users.create_user | API key | admin/support | UserCreate | UserRead | 201, 400 |
| POST | /apikeys | routers.apikeys.create_api_key | API key | admin | ApiKeyCreate | ApiKeyRead | 201, 400 |
| POST | /escrows | routers.escrow.create_escrow | API key | sender/admin | EscrowCreate | EscrowRead | 201 |
| POST | /escrows/{id}/deposit | routers.escrow.deposit | API key + optional Idempotency-Key | sender | EscrowDepositCreate | EscrowRead | 200, 409 |
| POST | /proofs | routers.proofs.submit_proof_route | API key | sender | ProofCreate | ProofRead | 201, 409, 422 |
| POST | /proofs/{id}/decision | routers.proofs.decide_proof_route | API key | support/admin | ProofDecision | ProofRead | 200, 400 |
| POST | /spend/allow | routers.spend.allow_usage | API key | sender/admin | AllowedUsageCreate | AllowedUsageRead | 201 |
| POST | /spend/purchases | routers.spend.create_purchase | API key + Idempotency-Key required | sender/admin | PurchaseCreate | PurchaseRead | 201, 400, 409 |
| POST | /spend | routers.spend.spend | API key + Idempotency-Key | sender/admin | SpendIn | PaymentRead | 200, 400, 409 |
| POST | /transactions | routers.transactions.create_transaction | API key + Idempotency-Key | admin | TransactionCreate | TransactionRead | 201, 400 |
| POST | /psp/webhook | routers.psp.psp_webhook | PSP secret(s) | - | raw JSON | {ok,event_id} | 200, 401, 503 |

## D. Data model & state machines
Entities overview

EscrowAgreement (status Enum, Decimal amounts, FK to creator, relationships to Milestone, EscrowEvent).

Milestone (ordering index, proof_type, proof_requirements JSON, optional geofence floats, Enum MilestoneStatus).

Proof (metadata JSON column metadata_, AI columns ai_risk_level, ai_score, ai_flags JSON, ai_explanation, ai_checked_at, reviewer metadata ai_reviewed_by, ai_reviewed_at).

UsageMandate, AllowedUsage, Purchase (Numeric amounts, unique constraints preventing overlapping mandates, total_spent tracking).

Payment (PaymentStatus Enum, idempotency_key, FKs to escrow/milestone/proof, PSP references).

Transaction, AuditLog, ApiKey, User, PSPWebhookEvent for compliance and ops.

State machines

Escrow: DRAFT → ACTIVE → WAITING_RELEASE → RELEASED/REFUNDED, transitions recorded via EscrowEvent and AuditLog inside app/services/escrow.py.

Proof: WAITING → PENDING_REVIEW → APPROVED/REJECTED; PHOTO may jump to APPROVED with auto-payment; manual decisions enforce reviewer note when overriding AI warnings.

Payment: PENDING → SENT → SETTLED/ERROR, with PSP webhook events updating status idempotently.

Mandate/Purchase: Mandate stays ACTIVE until total_spent reaches limit_amount; purchases are COMPLETED once created under idempotent key.

## E. Stability results
pytest -q → 67 passed, 1 skipped, 2 warnings (pydantic Config deprecation + async coroutine skip) (chunk 02faba).

Alembic chain verified: alembic upgrade head, alembic current, alembic heads, alembic history --verbose all succeed with head 1b7cc2cfcc6e (chunks def6b5, 3ea749, 027c09, 867746).

Static review highlights:

OCR/AI helpers wrap network failures in try/except, returning advisory defaults (no blocking failures).

sanitize_payload_for_audit masks IBAN/email/storage URL before logging; extend list for cities/vendors.

Lifespan uses a single async context manager; no lingering @app.on_event handlers.

## F. Security & integrity
AuthN/Z: require_scope dependencies enforce API-key scopes per router; actor_from_api_key standardizes AuditLog.actor.

Input validation: Pydantic models constrain fields (length, regex, Decimal). AI fields absent from ProofCreate, so clients cannot forge ai_risk_level.

File/proof validation: Photo proofs check EXIF timestamp, geofence distance (Haversine), and metadata presence; doc proofs remain manual with advisory checks.

Secrets/config: Settings loads PSP secrets (current + next), OpenAI key, OCR flags, and toggles for ALLOW_DB_CREATE_ALL; .env.example documents defaults with AI/OCR disabled.

Audit/logging: AuditLog entries created on proof submit/decision, escrow updates, spend, transactions, PSP events; payload sanitization masks obvious PII before persistence.

## G. Observability & operations
Logging pipeline centralizes formatting and levels; optional Prometheus exporter (starlette_exporter) and Sentry DSN in config.

HTTP errors standardized via error_response helpers and FastAPI exception handlers.

Alembic-managed schema with explicit guard against Base.metadata.create_all() unless APP_ENV is dev/test and ALLOW_DB_CREATE_ALL=True.

Deployment: .env.example spells out PSP/AI/OCR secrets; README references uvicorn entrypoint; tests cover migrations to ensure reproducibility.

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | /spend/purchases | Clients without Idempotency-Key now receive 400, potentially breaking legacy integrations. | Failed purchase retries → support load | Medium | P0 | Communicate rollout, consider transitional grace (accept header optional but warn) or automated client updates. |
| R2 | PSP webhook | Secret rotation supported but operational process absent; stale PSP_WEBHOOK_SECRET_NEXT leaves only one valid secret. | Compromised secret lets attacker fake SETTLED events | Medium | P0 | Document rotation runbook, add monitoring when both secrets missing, log warnings when NEXT unused past SLA. |
| R3 | AuditLog sanitization | Fields outside SENSITIVE_KEYS (e.g., supplier city, merchant label) remain unmasked; leaked logs can still reveal PII. | GDPR/privacy exposure | Low | P0 | Expand sanitizer or invert approach (explicit allowlist). Add regression tests verifying new masks. |
| R4 | Lifespan create_all | Mis-set ALLOW_DB_CREATE_ALL in staging/prod still enables runtime schema creation, bypassing Alembic. | Schema drift, missing migrations | Low | P0 | Enforce env guard (fail fast when non-dev env + flag true) or compile-time check in CI/CD. |
| R5 | AI override governance | Reviewers can approve warning/suspect proofs with a note, but there is no secondary approval or dashboard to review overrides. | AI escalations ignored without oversight | Medium | P0 | Introduce queue/report for overrides + optional dual approval, log metrics for overrides vs AI risk. |
| IA-1 | AI sanitizer | Fully masking supplier_name/beneficiary_name deprives AI of matching signals. | False positives/negatives | Low | P1 | Mask partially (keep few characters) or pass hashed versions plus expected hash for comparison. |
| OCR-1 | Invoice OCR | Feature flag might be toggled on even though _call_external_ocr_provider returns {}. | False belief in OCR coverage | Low | P1 | Auto-disable when provider none or raise startup warning; add provider implementation. |
| OBS-1 | Async tests | test_legacy_key_rejected_outside_dev skipped (async) so regression could slip. | Missed security regression | Low | P2 | Install pytest-asyncio or rewrite test sync to keep coverage. |

## I. AI Proof Advisor, OCR & risk scoring (dedicated section)
### I.1 AI architecture
Config toggles: AI_PROOF_ADVISOR_ENABLED=False by default, provider/model/timeouts configurable via Settings. OPENAI_API_KEY optional; fallback result returned when unset.

Modules:

ai_proof_flags.py: exposes ai_enabled(), ai_model(), ai_timeout_seconds() for deterministic gating.

aio_proof_advisor.py: contains long-lived prompt, context builder, sanitizer, OpenAI call with timeout + try/except + fallback JSON.

document_checks.py: backend comparisons feeding IA context.

invoice_ocr.py: optional metadata enrichment before backend checks.

### I.2 AI integration into proof flows
PHOTO branch: After EXIF/geofence validation and only when auto_approve=True, AI is called; metadata gains ai_assessment, and Proof.ai_* columns persist the verdict. Exceptions log but do not block.

NON-PHOTO branch: Always manual review; AI advisory triggered if flag enabled. compute_document_backend_checks output is passed to the AI. AI failures are logged and ignored, keeping behavior unchanged when disabled.

Reviewer governance: /proofs/{id}/decision enforces note when approving warnings/suspects, stamping ai_reviewed_by/at.

### I.3 OCR & backend_checks
OCR hook runs immediately after metadata_payload = dict(payload.metadata or {}) for document proof types, enriching metadata without overwriting non-empty user input.

_call_external_ocr_provider currently a stub returning {} unless a real provider is wired; fails gracefully.

compute_document_backend_checks synthesizes diffs for amount/currency, IBAN last4, invoice date ranges, and supplier names; these signals feed the AI context for better scoring.

### I.4 AI/OCR-specific risks
| ID | Domain (AI/OCR) | Risk | Impact | Likelihood | Priority | Recommended fix |
| --- | --- | --- | --- | --- | --- | --- |
| AI-OVR | AI override | Reviewers can override AI warnings with minimal oversight. | Fraud slipping through | Medium | P0 | Add dashboard + dual-approval or escalate to admin when overriding suspect proofs. |
| AI-DATA | Sanitization | Full masking of supplier/beneficiary names prevents AI from spotting mismatches. | Reduced AI accuracy | Low | P1 | Mask partially or provide hashed comparison tokens. |
| OCR-STUB | OCR provider | Flag could be enabled despite stub returning {}. | False sense of validation | Low | P1 | Add startup warning or auto-disable when provider none. |
| AI-TIMEOUT | Timeout/latency | Single timeout setting (12s) may cause long HTTP requests under load. | Endpoint latency spikes | Low | P2 | Instrument latency metrics, tune timeout, and add circuit breaker/backoff. |

## J. Roadmap to a staging-ready MVP
P0 checklist

Communicate & enforce Idempotency-Key requirement on /spend/purchases, including temporary dual-mode acceptance or client SDK update (R1).

Define PSP secret rotation SOP (schedules, alerts when NEXT secret unused) and validate both secrets configured in staging/prod (R2).

Expand sanitize_payload_for_audit coverage or switch to allowlisting; add regression tests for new keys (R3).

Fail fast when ALLOW_DB_CREATE_ALL=True outside {dev,local,test} to prevent schema drift; add CI guard (R4).

Build reviewer oversight for AI overrides (e.g., admin queue, second approval) so warning/suspect approvals are traceable (R5).

P1 checklist

Implement a real OCR provider or auto-disable when INVOICE_OCR_PROVIDER=none (OCR-1).

Add partial masking rather than full redaction for supplier/beneficiary names passed to AI (AI-DATA).

Consolidate Idempotency-Key utilities and ensure every money-moving endpoint shares the same retry semantics.

Add Prometheus metrics for AI/OCR latency and fallback counts.

P2 checklist

Provide a mock AI mode for local/testing without OpenAI.

Extend async test coverage by adopting pytest-asyncio for coroutine tests.

Automate PSP webhook secret rotation via scheduled job or deployment hook.

Verdict: GO for a staging with 10 real users, contingent on executing the P0 checklist (communication on idempotence, PSP rotation SOP, broader audit sanitization, hard guard on create_all, and AI override oversight).

## K. Verification evidence
Environment prep & dependencies: python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt (chunk 69592d).

Migrations: alembic upgrade head (chunk def6b5), alembic current (chunk 3ea749), alembic heads (chunk 027c09), alembic history --verbose (chunk 867746).

Tests: pytest -q → 67 passed, 1 skipped, 2 warnings (pydantic Config deprecation, async test skipped) (chunk 02faba).

Key code references via rg/sed:

app/services/proofs.py lines ≈30–220 for OCR hook, AI advisory, and metadata persistence (chunks f4e95a, 685a2f).

app/services/ai_proof_advisor.py for prompt, sanitation, fallback logic (chunks f6e88a, ddf39c).

app/services/invoice_ocr.py for standardized metadata format (chunk f86ca0).

app/services/document_checks.py for backend signal computation (chunk ff4e20).

app/utils/audit.py for payload masking and actor utilities (chunk bb9753).
