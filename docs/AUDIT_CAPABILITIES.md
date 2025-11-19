# Kobatela_alpha — Capability & Stability Audit (2026-03-31)

## A. Executive summary
- Core fintech flows (escrow, spend, proofs, payments, PSP webhook) use scoped API-key auth, idempotency keys, and typed money columns to reduce double-spend and drift risks.【F:app/routers/escrow.py†L15-L71】【F:app/services/proofs.py†L97-L219】【F:app/routers/transactions.py†L17-L67】【F:app/models/proof.py†L29-L46】
- Proof ingestion chains strict EXIF/geofence validation with optional OCR and AI advisory layers; AI outputs are server-side only and stored in dedicated read-only fields.【F:app/services/proofs.py†L137-L219】【F:app/models/proof.py†L29-L46】
- Runtime configuration is centralized via `Settings` with short-lived cache; PSP/AI/OCR flags are read per-call and surfaced in `/health` together with scheduler lock status for ops visibility.【F:app/config.py†L32-L119】【F:app/routers/health.py†L55-L71】
- PSP webhook handling now verifies HMAC signatures with timestamp skew protection and secret rotation support before persisting settlement events.【F:app/services/psp_webhooks.py†L27-L100】【F:app/routers/psp.py†L19-L60】
- Distributed scheduler uses DB lock with owner+TTL, heartbeat refresh, and health exposure to stay safe across runners.【F:app/services/scheduler_lock.py†L34-L154】【F:app/routers/health.py†L68-L71】

Major risks / limitations:
- AI/OCR privacy and masking rely on best-effort filtering; metadata allowlist is not comprehensive, so sensitive fields could still leak to the AI prompt.【F:app/services/ai_proof_advisor.py†L207-L220】
- Monetary values extracted via OCR are normalized but still originate from JSON metadata before landing in typed columns, leaving room for inconsistent upstream formats.【F:app/services/proofs.py†L137-L146】【F:app/services/invoice_ocr.py†L102-L134】
- PSP webhook verification depends on shared HMAC secrets without nonce tracking; replay attacks within the allowed timestamp window remain possible.【F:app/services/psp_webhooks.py†L58-L100】
- Audit coverage is uneven: proof decisions and payment executions log audits, but AI/OCR invocations and some reads lack dedicated audit entries for forensics.【F:app/services/proofs.py†L220-L310】
- Observability is limited: `/health` omits DB/alembic checks and there is no metrics/tracing pipeline, making incident triage harder.【F:app/routers/health.py†L55-L71】

Readiness score: **70 / 100** — strong functional coverage with recent PSP/scheduler hardening, but AI/OCR privacy, replay safeguards, and ops visibility need P0 attention before staging.

## B. Capability map (current features)
### B.1 Functional coverage
| Feature | Endpoints / modules involved | Status (OK / Partial / Missing) | Notes |
| --- | --- | --- | --- |
| Health & runtime introspection | `/health`, scheduler lock describe | Partial | Shows AI/OCR flags, PSP secret fingerprints, scheduler lock; lacks DB/migration probes.【F:app/routers/health.py†L55-L71】 |
| User & API key lifecycle | `/users`, `/apikeys` | Partial | CRUD with scope checks and audit on key actions; no pagination/search.【F:app/routers/apikeys.py†L41-L103】 |
| Escrow lifecycle | `/escrows/*` | OK | Create, deposit (idempotent), deliver/approve/reject, deadline check, read with audit.【F:app/routers/escrow.py†L15-L71】 |
| Mandates & spend controls | `/mandates`, `/spend/*`, `/transactions` | OK | Mandate setup/cleanup, spend categories/merchants/allowlist, purchases with idempotency and admin-led transactions.【F:app/routers/spend.py†L1-L200】【F:app/routers/transactions.py†L17-L67】 |
| Proof submission & decision | `/proofs` | OK | Photo validation (EXIF/geofence), OCR enrichment, optional AI advisory, manual decision endpoint.【F:app/services/proofs.py†L137-L219】【F:app/routers/proofs.py†L21-L46】 |
| Payments & PSP integration | `/payments/execute/{id}`, `/psp/webhook` | Partial | Manual payment execution plus webhook settlement; webhook HMAC lacks nonce/replay guard.【F:app/routers/payments.py†L14-L19】【F:app/services/psp_webhooks.py†L58-L100】 |
| Alerts & monitoring | `/alerts` | OK | List alerts filtered by type (static).【F:app/routers/alerts.py†L1-L60】 |
| AI & OCR toggles | `ai_proof_flags`, `invoice_ocr` | Partial | Runtime flags and OCR stub exist; masking/timeout coverage limited.【F:app/services/ai_proof_flags.py†L5-L19】【F:app/services/invoice_ocr.py†L17-L134】 |

### B.2 End-to-end journeys supported today
- Photo proof with auto-approve: submit proof → EXIF/geofence validation → optional AI advisory → milestone and payment progression when allowed.【F:app/services/proofs.py†L137-L219】
- Invoice proof with OCR: upload document → OCR normalization/merge → backend checks → AI context → manual decision flow.【F:app/services/proofs.py†L137-L219】【F:app/services/document_checks.py†L36-L170】
- Usage spend with policy: configure mandate/categories/merchants → allowlist payees → purchases/transactions with idempotency keys.【F:app/routers/spend.py†L1-L200】【F:app/routers/transactions.py†L17-L67】
- PSP settlement: webhook verifies HMAC+timestamp → event persisted → payment settlement/error updates with audit log on failure.【F:app/routers/psp.py†L19-L60】【F:app/services/psp_webhooks.py†L102-L187】
- Admin onboarding: create/revoke API keys and manage users with scope enforcement and audit of sensitive actions.【F:app/routers/apikeys.py†L41-L103】

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request model | Response model | HTTP codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/health` | `health.healthcheck` | None | – | – | dict | 200 |
| POST | `/users` | `users.create_user` | API key | admin/support | `UserCreate` | `UserRead` | 201, 400 |
| GET | `/users/{user_id}` | `users.get_user` | API key | admin/support | – | `UserRead` | 200, 404 |
| POST | `/apikeys` | `apikeys.create_api_key` | API key | admin | `CreateKeyIn` | `ApiKeyCreateOut` | 201, 400 |
| GET | `/apikeys/{api_key_id}` | `apikeys.get_apikey` | API key | admin | – | `ApiKeyRead` | 200, 404 |
| DELETE | `/apikeys/{api_key_id}` | `apikeys.revoke_apikey` | API key | admin | – | – | 204, 404 |
| POST | `/mandates` | `mandates.create_mandate` | API key | sender | `UsageMandateCreate` | `UsageMandateRead` | 201 |
| POST | `/mandates/cleanup` | `mandates.cleanup_expired_mandates` | API key | sender | – | `{expired}` | 202 |
| POST | `/escrows` | `escrow.create_escrow` | API key | sender | `EscrowCreate` | `EscrowRead` | 201 |
| POST | `/escrows/{id}/deposit` | `escrow.deposit` | API key + Idempotency-Key | sender | `EscrowDepositCreate` | `EscrowRead` | 200 |
| POST | `/escrows/{id}/mark-delivered` | `escrow.mark_delivered` | API key | sender | `EscrowActionPayload` | `EscrowRead` | 200 |
| POST | `/escrows/{id}/client-approve` | `escrow.client_approve` | API key | sender | optional payload | `EscrowRead` | 200 |
| POST | `/escrows/{id}/client-reject` | `escrow.client_reject` | API key | sender | optional payload | `EscrowRead` | 200 |
| POST | `/escrows/{id}/check-deadline` | `escrow.check_deadline` | API key | sender | – | `EscrowRead` | 200 |
| GET | `/escrows/{id}` | `escrow.read_escrow` | API key | sender/support/admin | – | `EscrowRead` | 200, 404 |
| POST | `/proofs` | `proofs.submit_proof` | API key | sender | `ProofCreate` | `ProofRead` | 201, 404, 409, 422 |
| POST | `/proofs/{id}/decision` | `proofs.decide_proof` | API key | support/admin | `ProofDecision` | `ProofRead` | 200, 400, 404 |
| POST | `/spend/categories` | `spend.create_category` | API key | admin/support | `SpendCategoryCreate` | `SpendCategoryRead` | 201 |
| POST | `/spend/merchants` | `spend.create_merchant` | API key | admin/support | `MerchantCreate` | `MerchantRead` | 201 |
| POST | `/spend/allow` | `spend.allow_usage` | API key | admin/support | `AllowedUsageCreate` | dict | 201 |
| POST | `/spend/purchases` | `spend.create_purchase` | API key + Idempotency-Key | sender/admin | `PurchaseCreate` | `PurchaseRead` | 201, 400 |
| POST | `/spend/allowed` | `spend.add_allowed_payee` | API key | admin/support | `AddPayeeIn` | dict | 201 |
| POST | `/spend` | `spend.spend` | API key + Idempotency-Key | sender/admin | `SpendIn` | dict | 200, 400 |
| POST | `/payments/execute/{id}` | `payments.execute_payment` | API key | sender | – | `PaymentRead` | 200 |
| POST | `/psp/webhook` | `psp.psp_webhook` | Secret header | PSP | raw JSON | dict | 200, 401, 503 |
| GET | `/alerts` | `alerts.list_alerts` | API key | admin/support | query `type` | list[`AlertRead`] | 200 |
| POST | `/allowlist` | `transactions.add_to_allowlist` | API key | admin | `AllowlistCreate` | dict | 201 |
| POST | `/certified` | `transactions.add_certification` | API key | admin | `CertificationCreate` | dict | 201 |
| POST | `/transactions` | `transactions.post_transaction` | API key + Idempotency-Key | admin | `TransactionCreate` | `TransactionRead` | 201, 400 |
| GET | `/transactions/{id}` | `transactions.get_transaction` | API key | admin | – | `TransactionRead` | 200, 404 |

## D. Data model & state machines
- Entities:
  - EscrowAgreement/Milestone: Numeric(18,2) amounts, geofence floats, JSON `proof_requirements`, status enums tie milestones to proofs and payments.【F:app/services/proofs.py†L148-L219】【F:app/models/proof.py†L29-L46】
  - Proof: unique sha256, JSON metadata, normalized invoice amount/currency columns, AI advisory fields (risk_level, score, flags, explanation, timestamps).【F:app/models/proof.py†L22-L46】
  - Payment: Numeric amounts, PSP reference/status enum, settlement/error handling via webhook service.【F:app/services/psp_webhooks.py†L133-L187】
  - SchedulerLock: unique name with owner, acquired_at, expires_at, timestamps for distributed locking.【F:app/models/scheduler_lock.py†L13-L21】
  - APIKey/User/Allowlists/Spend: scoped API keys, allowlist/certified recipients, purchases/transactions with idempotency keys (per routers/services).
- State machines:
  - Escrow: created → deposits → delivery → client approve/reject → payout via proof/payment flows.【F:app/routers/escrow.py†L15-L71】【F:app/services/proofs.py†L220-L310】
  - Milestone/Proof: WAITING → PENDING_REVIEW/APPROVED/REJECTED; photo can auto-approve after validations; AI advisory adds flags without auto-approval for documents.【F:app/services/proofs.py†L137-L219】
  - Payment: pending → settled/error via manual execution or PSP webhook updates.【F:app/services/psp_webhooks.py†L102-L187】
  - Scheduler lock: acquire/refresh/release with TTL and owner; describe for health output.【F:app/services/scheduler_lock.py†L34-L154】

## E. Stability results
- Static view of tests (not executed; inferred): coverage across health fingerprints, PSP webhook secrets/signatures, AI privacy/masking, OCR enrichment, scheduler lock contention/expiry, escrow/proof/payment lifecycles, spend idempotency, and transaction audit logs.【F:tests/test_health.py†L4-L16】【F:tests/test_ai_privacy.py†L1-L160】【F:tests/test_scheduler_lock.py†L1-L120】
- Skips/xfail: none observed in reviewed files (static inspection).
- Static review notes:
  - External calls (AI/OCR) wrapped in broad try/except, but masking allowlist is limited; risk of sensitive metadata leakage remains.【F:app/services/ai_proof_advisor.py†L207-L220】
  - Scheduler lock uses SessionLocal helper and TTL; relies on DB availability at startup/heartbeat without health probing.【F:app/services/scheduler_lock.py†L19-L154】
  - OCR stub returns empty data when disabled/unsupported, preventing crashes but leaving accuracy untested.【F:app/services/invoice_ocr.py†L17-L134】

## F. Security & integrity
- AuthN/Z: API-key header with scope enforcement across routers; sender/support/admin scopes control access to financial and proof endpoints.【F:app/routers/transactions.py†L17-L67】【F:app/routers/proofs.py†L21-L46】
- Input validation: Pydantic schemas enforce enums and required fields; monetary columns use Numeric/Decimal in models to avoid float drift.【F:app/models/proof.py†L29-L46】
- File/proof validation: sha256 uniqueness, EXIF/GPS/geofence checks for photos, backend checks for documents, OCR enrichment prior to AI context.【F:app/services/proofs.py†L137-L219】【F:app/services/document_checks.py†L36-L170】
- Secret management: Settings load PSP/AI/OCR secrets from env with strip validator; `/health` exposes fingerprints (first 8 hex) for rotation visibility.【F:app/config.py†L35-L89】【F:app/routers/health.py†L42-L71】
- Audit/logging: AuditLog used for proof approvals/payments and PSP failures; transaction reads now audited; gaps remain for AI/OCR calls and some reads.【F:app/services/proofs.py†L220-L310】【F:app/routers/transactions.py†L45-L67】

## G. Observability & operations
- Logging: standard logger usage in services (PSP, AI/OCR, proofs) without structured correlation IDs.【F:app/services/psp_webhooks.py†L52-L187】【F:app/services/proofs.py†L137-L310】
- Error handling: HTTPExceptions with error_response helper; AI/OCR failures fall back silently; webhook verification returns 401 with reason codes.【F:app/routers/psp.py†L28-L60】【F:app/services/ai_proof_advisor.py†L188-L220】
- Alembic migrations: sequential revisions include scheduler lock owner/expiry and proof AI/Invoice fields (static inspection; commands not run).【F:alembic/versions/4e1bd5489e1c_add_owner_and_expires_to_scheduler_locks.py†L1-L34】
- Deployment: lifespan uses scheduler heartbeat; `/health` reports scheduler status but no DB connectivity or migration drift checks.【F:app/routers/health.py†L55-L71】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority (P0/P1/P2) | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Monetary/OCR normalization | OCR-derived amounts/currency originate in JSON and may retain float/string quirks before coercion into typed fields, risking inconsistencies between metadata, AI context, and stored columns. | High | Medium | P0 | Centralize Decimal coercion and validation before persistence; enforce schema-level constraints and add tests around OCR edge cases.【F:app/services/proofs.py†L137-L146】【F:app/services/invoice_ocr.py†L47-L99】 |
| R2 | PSP webhook replay | HMAC+timestamp validation lacks nonce/replay tracking; windowed replays remain possible. | High | Medium | P0 | Add one-time nonce/event-id cache per timestamp window and enforce monotonic timestamps; document rotation/monitoring.【F:app/services/psp_webhooks.py†L58-L100】 |
| R3 | Audit coverage | AI/OCR invocations and some read paths are not audited, reducing forensics on sensitive actions. | Medium | Medium | P0 | Add AuditLog entries for AI/OCR attempts (without sensitive payload), escrow reads, and payment executions where missing.【F:app/services/proofs.py†L220-L310】 |
| R4 | AI/OCR privacy | Masking allowlist may omit sensitive metadata, enabling leakage to OpenAI; no rate-limit/timeout metrics. | High | Medium | P0 | Enforce explicit allowlist + redaction before `_sanitize_context`, add timeout/error metrics, and expand tests for sensitive keys.【F:app/services/ai_proof_advisor.py†L207-L220】 |
| R5 | Observability/health | `/health` omits DB/migration checks; scheduler lock depends on DB without readiness probe. | Medium | Medium | P0 | Add DB ping/alembic head check to health, expose lock age/expiry, and alert on stale ownership.【F:app/routers/health.py†L55-L71】【F:app/services/scheduler_lock.py†L34-L154】 |
| R6 | PSP secret ops | Missing requirement for both primary/next secrets in prod; rotation state only fingerprinted. | Medium | Low | P1 | Enforce at least one secret in non-dev and alert when only `next` is set; add metrics for signature failures.【F:app/routers/health.py†L55-L71】【F:app/services/psp_webhooks.py†L58-L100】 |
| R7 | Performance/timeout | AI timeout fixed at 12s; OCR stub lacks timeout; long calls could block proof submission under load. | Medium | Low | P1 | Add configurable timeout and circuit breaker around external calls; consider async/background execution.【F:app/config.py†L54-L67】【F:app/services/invoice_ocr.py†L102-L134】 |
| R8 | Data validation | Geofence/photo validations rely on raw floats and limited bounds; document checks accept wide inputs. | Medium | Low | P2 | Tighten Pydantic validators (lat/lon ranges, date formats) and add schema-level constraints for proof metadata fields.【F:app/services/proofs.py†L148-L219】【F:app/services/document_checks.py†L36-L170】 |

## I. AI Proof Advisor, OCR & risk scoring (dedicated section)
### I.1 AI architecture
- Config flags: `AI_PROOF_ADVISOR_ENABLED` (default False), provider/model, timeout, OpenAI API key, and OCR toggles (enabled/provider/key) all live in `Settings` and are read at runtime with TTL cache.【F:app/config.py†L54-L67】【F:app/services/ai_proof_flags.py†L5-L19】
- Modules: AI flags helper, AI Proof Advisor service (prompt, masking, OpenAI call), document backend checks, invoice OCR stub/normalizer, AI/OCR fields on Proof model for server-side storage.【F:app/services/ai_proof_advisor.py†L1-L220】【F:app/services/document_checks.py†L36-L170】【F:app/services/invoice_ocr.py†L17-L134】【F:app/models/proof.py†L29-L46】

### I.2 AI integration into proof flows
- Photo proofs: after EXIF/geofence validation, AI advisory optionally runs and attaches assessment to metadata and AI columns without blocking approval; auto-approve only if validations pass.【F:app/services/proofs.py†L148-L219】
- Document proofs (PDF/INVOICE/CONTRACT): OCR enrichment merges fields without overwriting user data, backend checks compute comparisons, and AI advisory (if enabled) enriches metadata; decisions remain manual.【F:app/services/proofs.py†L137-L219】【F:app/services/document_checks.py†L36-L170】
- AI outputs are server-set fields (`ai_risk_level`, `ai_score`, `ai_flags`, `ai_explanation`, `ai_checked_at`); clients cannot write them.【F:app/models/proof.py†L39-L46】

### I.3 OCR & backend_checks
- OCR toggle/provider from settings; default provider `none` returns empty result and marks status accordingly, avoiding hard failures.【F:app/services/invoice_ocr.py†L17-L134】
- Normalization maps totals, currency, date, invoice number, supplier, and IBAN last4/masked before merging into metadata without overwriting existing keys.【F:app/services/invoice_ocr.py†L47-L99】【F:app/services/invoice_ocr.py†L102-L134】
- Backend checks compute amount/iban/date/supplier comparisons against `proof_requirements`, returning structured flags for AI context; no exceptions on missing data.【F:app/services/document_checks.py†L36-L170】

### I.4 AI/OCR-specific risks
| ID | Domain (AI/OCR) | Risk | Impact | Likelihood | Priority | Recommended fix |
| --- | --- | --- | --- | --- | --- | --- |
| AI1 | Privacy | Masking allowlist may miss sensitive metadata fields, leaking to AI provider. | High | Medium | P0 | Enforce strict allowlist/redaction before `_sanitize_context`; add tests for IBAN/email/PII masking.【F:app/services/ai_proof_advisor.py†L207-L220】 |
| AI2 | Resilience | AI timeout/errors handled but without metrics; long calls could delay submissions. | Medium | Medium | P0 | Add metrics and stricter timeout/rate limiting; consider async/background AI evaluation.【F:app/config.py†L54-L67】【F:app/services/ai_proof_advisor.py†L188-L220】 |
| AI3 | Data consistency | OCR values flow from metadata into AI context and typed columns; divergent parsing could mislead scoring. | High | Medium | P0 | Single-source normalization helper reused for DB and AI context; validate currency length/Decimal coercion with tests.【F:app/services/proofs.py†L137-L146】 |
| AI4 | Auditability | AI/OCR calls not recorded in AuditLog, reducing traceability for risky automation. | Medium | Medium | P1 | Add audit events with non-sensitive payload for each AI/OCR invocation and fallback path.【F:app/services/proofs.py†L137-L219】 |
| AI5 | Provider stub | OCR provider is stubbed; real provider integration may fail silently due to catch-all logging. | Medium | Low | P2 | Implement provider-specific adapters with explicit error surfaces and contract tests.【F:app/services/invoice_ocr.py†L23-L37】 |

## J. Roadmap to a staging-ready MVP
- P0 checklist (blocking):
  - Enforce nonce/replay defense on PSP webhooks (cache event_id per timestamp window) and require at least one configured secret in non-dev environments.【F:app/services/psp_webhooks.py†L58-L100】
  - Harden AI/OCR privacy: strict allowlist/masking before OpenAI calls, plus metrics and timeout/rate-limit guards.【F:app/services/ai_proof_advisor.py†L207-L220】【F:app/config.py†L54-L67】
  - Normalize OCR monetary fields once and persist to typed columns before AI context; validate currency/Decimal parsing with unit tests.【F:app/services/proofs.py†L137-L146】【F:app/services/invoice_ocr.py†L47-L99】
  - Expand AuditLog to AI/OCR invocations, escrow reads, and payment execution paths for full lifecycle forensics.【F:app/services/proofs.py†L220-L310】
  - Add DB connectivity/alembic head check to `/health`; report scheduler lock age/expiry and stale detection.【F:app/routers/health.py†L55-L71】【F:app/services/scheduler_lock.py†L34-L154】
- P1 checklist (pre-pilot):
  - Structured logging/metrics for PSP failures, AI timeouts, OCR outcomes; alert on webhook signature failure rates.【F:app/services/psp_webhooks.py†L52-L187】
  - Pagination and listing endpoints for users/proofs/transactions; add search filters for alerts/logs.
  - Stronger validation on geofence/doc fields and mandate/proof requirements; document data retention and privacy posture.
- P2 checklist (comfort/scalability):
  - Circuit breakers/caching for external AI/OCR; background retries for transient PSP issues.
  - Config hot-reload metrics and correlation IDs for tracing.

- **Verdict: NO-GO for staging with 10 real users** until P0 items are completed and validated via targeted tests and dry-run webhooks.

## K. Verification evidence
- Alembic (conceptual): `alembic current/heads/history --verbose` would confirm head alignment and presence of scheduler lock and proof AI/OCR migrations (not executed; inferred from migration files).【F:alembic/versions/4e1bd5489e1c_add_owner_and_expires_to_scheduler_locks.py†L1-L34】
- Tests (conceptual): `pytest -q` would exercise health fingerprints, PSP signature handling, AI privacy, OCR enrichment, scheduler locking, escrow/proof/payment flows, and transaction audits (not executed; inferred from test suite layout).【F:tests/test_health.py†L4-L16】【F:tests/test_ai_privacy.py†L1-L160】【F:tests/test_scheduler_lock.py†L1-L120】
- Code anchors: Proof lifecycle and AI/OCR integration in `app/services/proofs.py`; AI prompt/masking in `app/services/ai_proof_advisor.py`; OCR normalization in `app/services/invoice_ocr.py`; backend checks in `app/services/document_checks.py`; PSP HMAC verification in `app/services/psp_webhooks.py`; runtime config and `/health` telemetry in `app/config.py` and `app/routers/health.py`; scheduler lock resilience in `app/services/scheduler_lock.py`.【F:app/services/proofs.py†L97-L219】【F:app/services/ai_proof_advisor.py†L1-L220】【F:app/services/invoice_ocr.py†L17-L134】【F:app/services/document_checks.py†L36-L170】【F:app/services/psp_webhooks.py†L27-L187】【F:app/routers/health.py†L55-L71】【F:app/services/scheduler_lock.py†L34-L154】
