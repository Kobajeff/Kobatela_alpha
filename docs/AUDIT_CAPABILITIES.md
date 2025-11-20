# Kobatela_alpha — Capability & Stability Audit (2025-11-20)

## A. Executive summary
- Scoped API-key security with per-endpoint scopes and idempotency headers on monetary writes protects escrow, spend, and transaction flows against accidental double actions.【F:app/routers/escrow.py†L21-L86】【F:app/routers/transactions.py†L25-L120】
- Invoice proofs use a single normalization pipeline that surfaces errors, rejects malformed money data with 422, and aligns normalized values across metadata, DB columns, and AI context.【F:app/services/proofs.py†L87-L123】【F:app/services/invoice_ocr.py†L102-L146】
- AI Proof Advisor sanitizes context through deny-by-default metadata masking plus PII masking of mandate/backend checks before OpenAI calls, with safe fallbacks when disabled or misconfigured.【F:app/services/ai_proof_advisor.py†L215-L236】【F:app/utils/masking.py†L114-L180】
- PSP webhooks enforce HMAC + timestamp drift limits, require event identifiers with replay protection, and process settlements/errors idempotently.【F:app/routers/psp.py†L21-L68】【F:app/services/psp_webhooks.py†L29-L173】【F:app/models/psp_webhook.py†L10-L32】
- `/health` exposes PSP secret fingerprints, AI/OCR toggles, DB + migration status, and scheduler lock details for runtime diagnostics without leaking secrets.【F:app/routers/health.py†L20-L109】【F:app/services/scheduler_lock.py†L17-L173】

Major risks / limitations:
- `ai_score` persists as Float and AI masking drops unknown keys without redaction visibility, leaving residual privacy and precision concerns.【F:app/models/proof.py†L39-L44】【F:app/utils/masking.py†L114-L180】
- Settings cache uses a global export with 60s TTL; modules relying on cached values may lag secret/flag rotations.【F:app/config.py†L96-L133】
- PSP secrets validated per request but only guarded at startup; replay defense relies on DB uniqueness with fixed drift allowing short-window replays.【F:app/main.py†L64-L143】【F:app/services/psp_webhooks.py†L72-L118】
- AI/OCR and scheduler flows are synchronous and DB-dependent; no circuit breakers/async isolation, so provider or DB failures can cascade despite logging fallbacks.【F:app/services/proofs.py†L206-L295】【F:app/services/scheduler_lock.py†L36-L116】
- Test and migration commands were **not executed**; stability conclusions rely on static inspection only.

Readiness score (staging MVP): **82 / 100** — Core flows and P0 mitigations exist (normalization, replay limits, masking, health), but privacy rigor, config refresh, and PSP/AI resilience need tightening before broader exposure.

## B. Capability map (current features)
### B.1 Functional coverage
| Feature | Endpoints / modules involved | Status (OK / Partial / Missing) | Notes |
| --- | --- | --- | --- |
| Health & runtime introspection | `/health` | OK | Reports PSP secret status/fingerprints, AI/OCR toggles, DB/migration status, scheduler lock description.【F:app/routers/health.py†L20-L109】 |
| User & API key lifecycle | `/users`, `/apikeys` | Partial | Admin/support CRUD exists; search/pagination depth not assessed. |
| Escrow lifecycle | `/escrows/*` | OK | Create/deposit/mark-delivered/approve/reject/deadline check with audit on reads and idempotent deposits.【F:app/routers/escrow.py†L21-L105】 |
| Proof submission & decision | `/proofs` | OK | EXIF/geofence validation, OCR enrichment, normalization + AI advisory, manual decision with AI note guard and audits.【F:app/services/proofs.py†L71-L510】【F:app/routers/proofs.py†L20-L48】 |
| Payments & PSP integration | `/payments/execute/{id}`, `/psp/webhook` | OK | Manual execution plus HMAC/timestamp verification, event_id replay defense, settlement/error handling with auditing.【F:app/routers/psp.py†L21-L68】【F:app/services/psp_webhooks.py†L120-L228】 |
| Transactions & spend controls | `/spend/*`, `/transactions` | OK | Allowlist/categories/merchants/purchases with idempotency and admin transaction CRUD plus audited reads.【F:app/routers/transactions.py†L25-L120】【F:app/routers/spend.py†L1-L220】 |
| AI & OCR toggles | `ai_proof_flags`, `invoice_ocr` | Partial | Runtime flags and OCR stub/normalizer exist; no external provider integration or metrics yet.【F:app/services/invoice_ocr.py†L17-L180】【F:app/services/ai_proof_advisor.py†L251-L360】 |
| Scheduler | Lifespan + DB lock | OK | Owner+TTL lock with refresh/release and health description; single-runner APScheduler design.【F:app/services/scheduler_lock.py†L17-L173】【F:app/main.py†L99-L143】 |

### B.2 End-to-end journeys supported today
- Photo proof: submit → EXIF/geofence validation → optional AI advisory → auto-approve if validations pass → payout execution with idempotent keying and audit logging.【F:app/services/proofs.py†L137-L449】
- Invoice/contract proof: submit → OCR enrichment → normalization → backend checks → AI advisory (manual review) → AI fields/metadata persisted with audits for OCR/AI steps.【F:app/services/proofs.py†L94-L380】
- PSP settlement: webhook verifies signature/timestamp, deduplicates event_id, and settles or errors payments; failures audited and processed idempotently.【F:app/routers/psp.py†L21-L68】【F:app/services/psp_webhooks.py†L72-L228】
- Spend/transaction control: allowlist/categories/merchants plus purchases/transactions with idempotency and admin scopes, audited on reads.【F:app/routers/transactions.py†L25-L120】
- Scheduler housekeeping: DB lock acquisition/refresh/release with TTL and health visibility for multi-runner safety.【F:app/services/scheduler_lock.py†L17-L173】【F:app/routers/health.py†L87-L109】

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request model | Response model | HTTP codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/health` | `health.healthcheck` | None | – | – | dict | 200 |
| POST | `/escrows` | `escrow.create_escrow` | API key | sender | `EscrowCreate` | `EscrowRead` | 201 |
| POST | `/escrows/{id}/deposit` | `escrow.deposit` | API key + Idempotency-Key | sender | `EscrowDepositCreate` | `EscrowRead` | 200 |
| POST | `/escrows/{id}/mark-delivered` | `escrow.mark_delivered` | API key | sender | `EscrowActionPayload` | `EscrowRead` | 200 |
| POST | `/escrows/{id}/client-approve` | `escrow.client_approve` | API key | sender | optional body | `EscrowRead` | 200 |
| POST | `/escrows/{id}/client-reject` | `escrow.client_reject` | API key | sender | optional body | `EscrowRead` | 200 |
| POST | `/escrows/{id}/check-deadline` | `escrow.check_deadline` | API key | sender | – | `EscrowRead` | 200 |
| GET | `/escrows/{id}` | `escrow.read_escrow` | API key | sender/support/admin | – | `EscrowRead` | 200, 404 |
| POST | `/proofs` | `proofs.submit_proof` | API key | sender | `ProofCreate` | `ProofRead` | 201, 404, 409, 422 |
| POST | `/proofs/{id}/decision` | `proofs.decide_proof` | API key | support/admin | `ProofDecision` | `ProofRead` | 200, 400, 404 |
| POST | `/payments/execute/{id}` | `payments.execute_payment` | API key | sender | – | `PaymentRead` | 200 |
| POST | `/psp/webhook` | `psp.psp_webhook` | Secret headers | PSP | raw JSON | dict | 200, 400, 401, 503 |
| POST | `/spend/categories` | `spend.create_category` | API key | admin/support | `SpendCategoryCreate` | `SpendCategoryRead` | 201 |
| POST | `/spend/merchants` | `spend.create_merchant` | API key | admin/support | `MerchantCreate` | `MerchantRead` | 201 |
| POST | `/spend/allow` | `spend.allow_usage` | API key | admin/support | `AllowedUsageCreate` | dict | 201 |
| POST | `/spend/purchases` | `spend.create_purchase` | API key + Idempotency-Key | sender/admin | `PurchaseCreate` | `PurchaseRead` | 201, 400 |
| POST | `/spend/allowed` | `spend.add_allowed_payee` | API key | admin/support | `AddPayeeIn` | dict | 201 |
| POST | `/spend` | `spend.spend` | API key + Idempotency-Key | sender/admin | `SpendIn` | dict | 200, 400 |
| POST | `/allowlist` | `transactions.add_to_allowlist` | API key | admin | `AllowlistCreate` | dict | 201 |
| POST | `/certified` | `transactions.add_certification` | API key | admin | `CertificationCreate` | dict | 201 |
| POST | `/transactions` | `transactions.post_transaction` | API key + Idempotency-Key | admin | `TransactionCreate` | `TransactionRead` | 201, 400 |
| GET | `/transactions/{id}` | `transactions.get_transaction` | API key | admin | – | `TransactionRead` | 200, 404 |

## D. Data model & state machines
- Entities:
  - Proof: unique sha256, JSON metadata, normalized invoice_total_amount (Numeric 18,2) and invoice_currency (String(3)), AI advisory fields (risk level/score/flags/explanation timestamps) plus AI review markers.【F:app/models/proof.py†L22-L47】
  - EscrowAgreement/Deposit/Event: Numeric totals with status enum and timeline events; deposits enforce positive amounts and idempotency keys.【F:app/models/escrow.py†L12-L69】
  - Milestone (via services): sequencing and status gating handled in `submit_proof` with PENDING_REVIEW/APPROVED transitions.【F:app/services/proofs.py†L299-L338】
  - Payment: Numeric amount, unique psp_ref/idempotency_key, enum status with positive-amount check and indices.【F:app/models/payment.py†L11-L40】
  - PSPWebhookEvent: unique event_id with indices for replay protection and payload persistence.【F:app/models/psp_webhook.py†L10-L32】
  - SchedulerLock: name/owner/acquired_at/expires_at with TTL semantics for multi-runner safety.【F:app/models/scheduler_lock.py†L11-L24】【F:app/services/scheduler_lock.py†L17-L173】
- State machines:
  - Proof: SUBMITTED/PENDING_REVIEW → APPROVED/REJECTED; photo proofs may auto-approve after validations/AI; decisions log audits and enforce AI note when flagged.【F:app/services/proofs.py†L137-L510】
  - Payment: PENDING/SENT → SETTLED/ERROR via manual execution or PSP webhooks with finalization helpers and audits on failure.【F:app/services/psp_webhooks.py†L174-L228】
  - Scheduler lock: acquire → refresh → release with TTL/owner checks; described in health for observability.【F:app/services/scheduler_lock.py†L36-L173】【F:app/routers/health.py†L87-L109】

## E. Stability results
- Static view of tests (not executed): suite covers AI privacy/masking, invoice OCR normalization, proof flows (EXIF, AI review), PSP signature/replay, scheduler locks, spend/transactions, and health telemetry (see `test_ai_privacy.py`, `test_invoice_ocr.py`, `test_psp_webhook.py`, `test_scheduler_lock.py`).【F:tests/test_ai_privacy.py†L12-L110】【F:tests/test_invoice_ocr.py†L1-L120】【F:tests/test_psp_webhook.py†L1-L200】【F:tests/test_scheduler_lock.py†L1-L140】
- No skipped/xfail markers observed via static scan.
- Static review notes:
  - AI/OCR calls catch broad exceptions to avoid crashes but hide provider error detail; no metrics or retries/circuit breakers.【F:app/services/ai_proof_advisor.py†L334-L360】【F:app/services/invoice_ocr.py†L158-L180】
  - Health DB/migration checks degrade status instead of crashing but depend on DB availability; migration head is hardcoded.【F:app/routers/health.py†L20-L109】
  - Settings cache TTL and global export may delay config rotations; some modules rely on cached values.【F:app/config.py†L96-L133】

## F. Security & integrity
- AuthN/Z: API keys with scope checks on each router; actor extraction for audits; PSP webhooks gated by secrets/signatures with 401 on failures.【F:app/routers/escrow.py†L21-L105】【F:app/routers/psp.py†L21-L47】
- Input validation: Pydantic schemas enforce required fields; idempotency headers on monetary POSTs; proof decisions validated for approve/reject with AI note requirement when flagged.【F:app/routers/transactions.py†L56-L90】【F:app/services/proofs.py†L455-L510】
- File/proof validation: Geofence/EXIF checks reject invalid photos; document proofs run backend checks and enforce normalization before persisting; AI errors never block submission.【F:app/services/proofs.py†L137-L205】【F:app/services/document_checks.py†L36-L170】
- Secret management: Settings define PSP/AI/OCR keys (defaults disabled), fingerprints exposed via health; startup guard enforces PSP secrets outside dev though settings cache can delay rotations.【F:app/config.py†L35-L118】【F:app/main.py†L64-L143】【F:app/routers/health.py†L20-L109】
- Audit/logging: Escrow/transaction reads audited; proof submission/decision, OCR runs, AI analyses, and PSP payment failures recorded with sanitized payloads.【F:app/routers/escrow.py†L88-L105】【F:app/services/proofs.py†L334-L405】【F:app/services/psp_webhooks.py†L215-L228】

## G. Observability & operations
- Logging: Standard logging across services; no correlation IDs; masking helpers redact PSP secrets and proof metadata where applicable.【F:app/services/psp_webhooks.py†L60-L118】【F:app/utils/masking.py†L66-L112】
- HTTP error handling: Central exception handlers return structured error_response; webhook returns 401 on signature failure and 503 when secrets missing.【F:app/main.py†L155-L170】【F:app/routers/psp.py†L31-L47】
- Alembic migrations: Head revision `4e1bd5489e1c` adds scheduler lock owner/expiry; initial schema includes proof AI fields and PSP webhook events (inferred; not executed).【F:alembic/versions/4e1bd5489e1c_add_owner_and_expires_to_scheduler_locks.py†L1-L31】【F:alembic/versions/baa4932d9a29_0001_init_schema.py†L31-L46】
- Deployment/lifecycle: Lifespan enforces PSP secrets outside dev, initializes DB, manages scheduler lock heartbeat/cleanup; health exposes degraded state instead of failing hard.【F:app/main.py†L58-L144】【F:app/routers/health.py†L49-L109】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority (P0/P1/P2) | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Monetary safety | `ai_score` stored as Float; invoice normalization blocks invalid currency/amount but AI outputs keep float precision limits. | Medium | Medium | P0 | Migrate AI scoring to Decimal/Numeric; keep normalization strict and extend rounding/currency edge-case tests.【F:app/models/proof.py†L39-L44】【F:app/services/proofs.py†L87-L123】 |
| R2 | PSP webhook | Secrets validated per request but rotation/cache lag plus fixed drift; replay relies solely on DB uniqueness. | High | Medium | P0 | Add nonce/TTL cache and metrics; reduce drift; ensure secrets required in staging/prod even after cache refresh.【F:app/services/psp_webhooks.py†L29-L118】【F:app/main.py†L64-L143】 |
| R3 | Business lifecycle audit | AI/OCR success audits exist but payment settlement success not audited; AI masking drops unknown keys silently. | Medium | Medium | P0 | Add AuditLog for payment settlements with sanitized payload; log dropped AI metadata keys and extend privacy tests to backend/mandate contexts.【F:app/services/psp_webhooks.py†L174-L228】【F:app/utils/masking.py†L153-L180】 |
| R4 | FastAPI lifecycle/config refresh | Global settings export with TTL may serve stale secrets/flags; scheduler/AI/OCR lack circuit breakers. | Medium | Medium | P0 | Remove reliance on exported `settings`, force per-call `get_settings`, add failure budgets/metrics and optional async/offline AI/OCR workers.【F:app/config.py†L96-L133】【F:app/services/ai_proof_advisor.py†L334-L360】 |
| R5 | AI & OCR privacy | Deny-by-default masking drops unknown keys without redaction visibility; sensitive patterns may appear in mandate/backend contexts. | High | Medium | P0 | Redact unknown keys with placeholder and audit dropped keys; extend masking to all contexts and add PII-focused regression tests (IBAN/email/phone/custom fields).【F:app/services/ai_proof_advisor.py†L215-L236】【F:app/utils/masking.py†L153-L180】 |
| R6 | Observability | No metrics/tracing; migration head hardcoded; health depends on DB availability. | Medium | Medium | P1 | Add metrics for AI/OCR/PSP outcomes, dynamic Alembic head lookup, and degraded-but-200 health paths when DB unavailable.【F:app/routers/health.py†L20-L109】 |

## I. AI Proof Advisor, OCR & risk scoring (dedicated section)
### I.1 AI architecture
- Settings default AI_PROOF_ADVISOR_ENABLED=False with provider/model/timeout; OpenAI key optional. OCR flags default disabled/provider "none".【F:app/config.py†L54-L68】
- Modules: AI Proof Advisor sanitizes context and calls OpenAI; masking utilities enforce allowlist/redaction; invoice OCR stub/normalizer; backend checks compute structured comparisons.【F:app/services/ai_proof_advisor.py†L215-L360】【F:app/utils/masking.py†L114-L180】【F:app/services/invoice_ocr.py†L17-L180】【F:app/services/document_checks.py†L36-L170】

### I.2 AI integration into proof flows
- Photo proofs: After validation, AI advisory runs when enabled; results stored in metadata and AI columns; AI exceptions logged and never block submission/approval flow.【F:app/services/proofs.py†L206-L249】【F:app/services/proofs.py†L334-L352】
- Document proofs (PDF/INVOICE/CONTRACT): OCR enrichment then normalization; backend checks computed and passed to AI context; AI advisory stored in metadata/AI fields while decisions remain manual.【F:app/services/proofs.py†L94-L380】
- AI outputs are read-only to clients via schema; create payload does not accept AI fields.【F:app/models/proof.py†L39-L46】【F:app/schemas/proof.py†L29-L48】

### I.3 OCR & backend_checks
- OCR toggle/provider driven by settings; provider "none" returns empty; normalized invoice fields mapped with totals/currency/date/supplier/IBAN last4 and status/provider flags without overwriting user data.【F:app/services/invoice_ocr.py†L17-L180】
- Backend checks compare expected requirements vs metadata (amount, currency, IBAN last4, dates, supplier) yielding structured flags for AI context; tolerant to missing fields.【F:app/services/document_checks.py†L36-L170】

### I.4 AI/OCR-specific risks
| ID | Domain (AI/OCR) | Risk | Impact | Likelihood | Priority | Recommended fix |
| --- | --- | --- | --- | --- | --- | --- |
| AI1 | Privacy | Unknown metadata keys are dropped without explicit redaction logging; mandate/backend contexts may leak new fields. | High | Medium | P0 | Redact-and-log unknown keys across all contexts before OpenAI; expand tests for IBAN/email/phone/custom keys.【F:app/services/ai_proof_advisor.py†L215-L236】【F:app/utils/masking.py†L153-L180】 |
| AI2 | Resilience | AI call synchronous with limited timeout, no retries/metrics; failures only logged. | Medium | Medium | P0 | Add metrics and optional retries/circuit breaker; consider async/offline AI processing.【F:app/services/ai_proof_advisor.py†L334-L360】 |
| AI3 | Data consistency | AI score stored as Float; normalization strict but AI outputs may lose precision. | Medium | Medium | P0 | Migrate AI score to Decimal/Numeric and align schema/tests.【F:app/models/proof.py†L39-L44】 |
| AI4 | Auditability | AI/OCR executions audited, but payment settlement audits absent and AI masking drops unknown keys silently. | Medium | Medium | P1 | Add settlement audits and logging of dropped keys for forensic visibility.【F:app/services/psp_webhooks.py†L174-L228】【F:app/utils/masking.py†L153-L180】 |
| AI5 | Provider integration | OCR provider stub only; real provider integration untested. | Medium | Low | P2 | Add provider adapters with schema validation and contract tests before enabling externally.【F:app/services/invoice_ocr.py†L23-L37】 |

## J. Roadmap to a staging-ready MVP
- P0 checklist (blocking):
  - Enforce per-call settings refresh (avoid exported `settings`) and shorten TTL to ensure PSP/AI/OCR flags and secrets rotate promptly.【F:app/config.py†L96-L133】
  - Strengthen PSP webhook replay/secret governance: lower drift, add nonce/TTL cache or metrics, and ensure staging/prod startup fails without secrets even after cache refresh.【F:app/services/psp_webhooks.py†L29-L118】【F:app/main.py†L64-L143】
  - Harden AI privacy: redact-and-log unknown metadata keys across all contexts; extend PII regression tests (IBAN/email/phone/custom keys).【F:app/services/ai_proof_advisor.py†L215-L236】【F:app/utils/masking.py†L153-L180】【F:tests/test_ai_privacy.py†L12-L55】
  - Monetary/AI consistency: migrate AI score to Decimal/Numeric and keep normalization strict with edge-case rounding/currency tests.【F:app/models/proof.py†L39-L44】【F:app/services/invoice_ocr.py†L102-L146】
  - Observability: add metrics for AI/OCR/PSP outcomes and make health degrade gracefully without DB; dynamically read Alembic head instead of hardcoded revision.【F:app/routers/health.py†L49-L109】
- P1 checklist (pre-pilot):
  - Add settlement success audits and dropped-key logging; enrich webhook/AI/OCR metrics and alerts.
  - Provide pagination/search on listing endpoints; stricter validators on document metadata and geofence inputs.
  - Consider async/background AI/OCR to reduce request latency and isolate provider failures.
- P2 checklist (comfort/scalability):
  - Introduce circuit breakers/retries for external providers; correlation IDs/structured logging; configurable scheduler lock names per environment.
  - Document data retention/privacy for AI/OCR payloads and audit log scopes.

- **Verdict: NO-GO for a staging with 10 real users** until P0 items (config refresh, PSP replay/secret tightening, AI privacy redaction/logging, AI score precision, and observability/metrics) are delivered and validated by targeted tests.

## K. Verification evidence
- Migrations (conceptual): `alembic current`, `alembic heads`, and `alembic history --verbose` would confirm head `4e1bd5489e1c` (scheduler lock owner/expiry) and presence of proof AI fields and PSP webhook events from initial schema; commands **not executed** for this audit.【F:alembic/versions/4e1bd5489e1c_add_owner_and_expires_to_scheduler_locks.py†L1-L31】【F:alembic/versions/baa4932d9a29_0001_init_schema.py†L31-L46】
- Tests (conceptual): `pytest -q` would exercise AI privacy/masking, invoice normalization, PSP signature/replay, scheduler lock behavior, escrow/proof/payment flows, and health telemetry based on the test suite layout; tests **not run** here.【F:tests/test_ai_privacy.py†L12-L110】【F:tests/test_invoice_ocr.py†L1-L120】【F:tests/test_psp_webhook.py†L1-L200】【F:tests/test_scheduler_lock.py†L1-L140】
- Code anchors: References cite routers/services/models for proof lifecycle, AI/OCR integration, masking, normalization, PSP verification, and health telemetry demonstrating current behaviors and remaining gaps.【F:app/services/proofs.py†L87-L405】【F:app/services/ai_proof_advisor.py†L215-L360】【F:app/utils/masking.py†L114-L180】【F:app/services/invoice_ocr.py†L102-L180】【F:app/services/psp_webhooks.py†L29-L228】【F:app/routers/health.py†L20-L109】【F:app/services/scheduler_lock.py†L17-L173】
