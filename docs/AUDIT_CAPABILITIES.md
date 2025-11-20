# Kobatela_alpha — Capability & Stability Audit (2026-11-20)

## A. Executive summary
- Escrow, spend, proof, and PSP flows use scoped API-key auth with idempotency on monetary endpoints, reducing double-spend risk and tying actions to actors.【F:app/routers/escrow.py†L14-L70】【F:app/routers/transactions.py†L17-L69】
- Proof ingestion enforces EXIF/geofence validation, merges OCR-enriched metadata, normalizes invoice totals/currency, and feeds the same normalized values into AI context and persisted columns.【F:app/services/proofs.py†L86-L219】【F:app/services/invoice_ocr.py†L102-L134】
- AI Proof Advisor and masking now sanitize metadata with whitelist/redaction before sending to OpenAI, and fall back safely when disabled or misconfigured.【F:app/services/ai_proof_advisor.py†L215-L292】【F:app/utils/masking.py†L112-L169】
- PSP webhook handling validates HMAC+timestamp, deduplicates events by event_id with DB uniqueness, and updates payments with audit on failures.【F:app/routers/psp.py†L20-L61】【F:app/services/psp_webhooks.py†L68-L205】【F:app/models/psp_webhook.py†L9-L20】
- `/health` now reports PSP secret fingerprints/status, AI/OCR toggles, DB connectivity, migration head, and scheduler lock state for operational visibility.【F:app/routers/health.py†L20-L106】【F:app/services/scheduler_lock.py†L15-L94】

Major risks / limitations:
- AI masking allowlist is still best-effort; unlisted metadata keys are dropped rather than explicitly audited, and runtime context still includes non-masked backend fields.【F:app/services/ai_proof_advisor.py†L215-L236】
- Settings are cached globally with a TTL; secrets loaded once at startup may lag rotations until refresh, and global `settings` variable remains exported.【F:app/config.py†L96-L132】
- PSP webhook secrets are optional in config; missing secrets yield 503 but no staging/production guard, and drift window may still allow short replays despite event_id uniqueness.【F:app/routers/psp.py†L29-L43】【F:app/services/psp_webhooks.py†L68-L114】
- AI/OCR and scheduler rely on synchronous DB access; heavy load or DB failures could cascade (no circuit breakers/async paths).【F:app/services/proofs.py†L181-L219】【F:app/services/scheduler_lock.py†L18-L94】
- Test and migration commands were not executed for this audit; stability statements rely on static inspection only.

Readiness score: **78 / 100** — functional coverage is broad and P0 fixes for replay, monetary normalization, and observability are present, but privacy hardening, config refresh, and runtime resilience need tightening before wider staging.

## B. Capability map (current features)
### B.1 Functional coverage
| Feature | Endpoints / modules involved | Status (OK / Partial / Missing) | Notes |
| --- | --- | --- | --- |
| Health & runtime introspection | `/health` | OK | Includes PSP secret fingerprints, AI/OCR flags, DB/migration checks, scheduler lock status.【F:app/routers/health.py†L20-L106】 |
| User & API key lifecycle | `/users`, `/apikeys` | Partial | Scoped admin/support CRUD; limited pagination/search.
| Escrow lifecycle | `/escrows/*` | OK | Create, deposit (idempotency), deliver/approve/reject, deadline check, read with audit log.【F:app/routers/escrow.py†L14-L70】 |
| Proof submission & decision | `/proofs` | OK | EXIF/geofence validation, OCR enrichment, normalized invoice fields, AI advisory, manual decision endpoint with masking on responses.【F:app/routers/proofs.py†L20-L48】【F:app/services/proofs.py†L86-L219】 |
| Payments & PSP integration | `/payments/execute/{id}`, `/psp/webhook` | OK | Manual execution plus HMAC/timestamp verification and replay-protected webhook processing that settles or errors payments with audit on failure.【F:app/routers/psp.py†L20-L61】【F:app/services/psp_webhooks.py†L68-L205】 |
| Transactions & spend controls | `/spend/*`, `/transactions` | OK | Categories/merchants/allowlist, purchases with idempotency, admin transactions with audit on reads.【F:app/routers/transactions.py†L17-L69】 |
| AI & OCR toggles | `ai_proof_flags`, `invoice_ocr` | Partial | Runtime flags and OCR stub/normalizer exist; no external provider implementation or metrics yet.【F:app/services/invoice_ocr.py†L23-L163】【F:app/services/ai_proof_advisor.py†L251-L292】 |
| Scheduler | Lifespan + DB lock | OK | Owner+TTL lock with refresh/release and health description; still single-worker synchronous design.【F:app/services/scheduler_lock.py†L18-L154】 |

### B.2 End-to-end journeys supported today
- Photo proof: submit → EXIF/geofence validation → optional AI advisory → auto-approve if validations pass and milestone/payout continue via services.【F:app/services/proofs.py†L106-L219】
- Invoice/contract proof: submit → OCR enrichment → normalized totals/currency → backend checks → AI advisory (manual decision) → stored AI fields/metadata.【F:app/services/proofs.py†L93-L219】【F:app/services/invoice_ocr.py†L102-L163】
- PSP settlement: webhook verifies signature/timestamp, deduplicates event_id, marks payments settled or errored with audit on failures.【F:app/routers/psp.py†L20-L61】【F:app/services/psp_webhooks.py†L68-L205】
- Spend/transaction control: mandates/categories/merchants/allowlist plus purchases/transactions with idempotency and admin scopes.【F:app/routers/transactions.py†L17-L69】
- Scheduler housekeeping: DB lock acquisition/refresh with health visibility for multi-runner safety.【F:app/services/scheduler_lock.py†L18-L154】【F:app/routers/health.py†L87-L106】

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
| POST | `/psp/webhook` | `psp.psp_webhook` | Secret headers | PSP | raw JSON | dict | 200, 401, 503 |
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
  - Proof: unique sha256, JSON metadata, normalized invoice_total_amount (Numeric 18,2) and invoice_currency (String(3)), AI advisory fields (risk level/score/flags/explanation timestamps).【F:app/models/proof.py†L11-L48】
  - Escrow/Milestone: Numeric amounts with statuses linked to proofs/payments (see services).【F:app/services/proofs.py†L75-L219】
  - Payment: PSP reference/status updated by webhook handlers with audit on failures.【F:app/services/psp_webhooks.py†L138-L205】
  - PSPWebhookEvent: unique event_id with indices for replay protection and payload persistence.【F:app/models/psp_webhook.py†L9-L20】
  - SchedulerLock: unique name, owner, acquired_at, expires_at timestamps for distributed locks.【F:app/models/scheduler_lock.py†L11-L24】
  - APIKey/User/Spend/Transactions: scoped auth, allowlists, categories/merchants, idempotency keys in routers.
- State machines:
  - Proof: SUBMITTED/PENDING_REVIEW → APPROVED/REJECTED; photo may auto-approve after validations; AI adds advisory metadata only.【F:app/services/proofs.py†L106-L219】
  - Payment: pending → settled/error via manual execution or PSP webhook updates with audit on failure.【F:app/services/psp_webhooks.py†L138-L205】
  - Scheduler lock: acquire/refresh/release with TTL and ownership; described for health checks.【F:app/services/scheduler_lock.py†L18-L154】

## E. Stability results
- Static view of tests: suite covers escrow, proofs (EXIF, AI review), OCR, AI masking/privacy, PSP webhook signatures/replay, scheduler locks, spend/transactions, and health telemetry (per filenames in `tests/`). No skipped markers observed from static scan.
- Static review notes:
  - Broad try/except around AI and OCR prevents crashes but hides provider errors; logging exists but no metrics.【F:app/services/ai_proof_advisor.py†L259-L292】【F:app/services/invoice_ocr.py†L147-L163】
  - DB sessions are passed explicitly; synchronous blocking remains for webhook and scheduler paths.
  - No commands executed during this audit; stability inferred from code and tests structure only.

## F. Security & integrity
- AuthN/Z: API keys with scopes enforced per endpoint; PSP webhook uses secret headers; scheduler not exposed publicly.【F:app/routers/proofs.py†L20-L48】【F:app/routers/psp.py†L20-L61】
- Input validation: Pydantic schemas enforce length/patterns; proof decisions restrict values; idempotency required on monetary POSTs.【F:app/schemas/proof.py†L43-L48】【F:app/routers/transactions.py†L43-L58】
- File/proof validation: EXIF/geofence rules with hard failures for geofence/age issues; metadata sanitized for responses and AI.【F:app/services/proofs.py†L106-L219】【F:app/utils/masking.py†L64-L110】
- Secrets/config: Settings define PSP/AI/OCR keys with defaults disabled; cached with TTL and accessible via health fingerprints.【F:app/config.py†L35-L116】【F:app/routers/health.py†L20-L106】
- Audit/logging: Transaction reads and PSP failures log audits; escrow reads log audit entries; AI/OCR outcomes logged in metadata but not yet in AuditLog explicitly.【F:app/routers/transactions.py†L57-L69】【F:app/routers/escrow.py†L62-L70】

## G. Observability & operations
- Logging: Standard logging in services; no correlation IDs or structured log schema.【F:app/services/psp_webhooks.py†L56-L205】
- HTTP error handling: Uses HTTPException with error_response codes; webhook returns 401 on signature failures and 503 when secrets missing.【F:app/routers/psp.py†L29-L44】
- Alembic migrations: Head revision `4e1bd5489e1c` adds scheduler lock owner/expiry; initial schema includes PSP webhook events and proof AI fields (inferred from files, not executed).【F:alembic/versions/4e1bd5489e1c_add_owner_and_expires_to_scheduler_locks.py†L1-L31】【F:alembic/versions/baa4932d9a29_0001_init_schema.py†L31-L46】
- Deployment/lifecycle: Scheduler lock acquired with TTL, refreshed/released on shutdown; health exposes DB/migration status and lock description.【F:app/services/scheduler_lock.py†L18-L154】【F:app/routers/health.py†L87-L106】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority (P0/P1/P2) | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Monetary normalization | OCR/user metadata still drives invoice totals/currency; if malformed, values drop to None and AI/DB may diverge silently. | High | Medium | P0 | Enforce validation errors when currency code invalid; add explicit audit/log on normalization failures and schema-level constraints/tests.【F:app/services/proofs.py†L93-L104】【F:app/services/invoice_ocr.py†L102-L129】 |
| R2 | PSP webhook secrets/anti-replay | Secrets optional; drift window allows short replays despite event_id uniqueness; no environment guard for missing secrets. | High | Medium | P0 | Require secret presence in non-dev, tighten timestamp window, and add nonce cache beyond DB uniqueness; emit metrics on signature failures.【F:app/routers/psp.py†L29-L43】【F:app/services/psp_webhooks.py†L68-L114】 |
| R3 | Business audit coverage | AI/OCR invocations and payment success paths lack AuditLog entries; only certain reads are logged. | Medium | Medium | P0 | Add AuditLog for AI/OCR runs and payment settlements (not just failures) with sanitized payloads; ensure proof decisions already covered remain consistent.【F:app/services/proofs.py†L86-L219】【F:app/services/psp_webhooks.py†L138-L205】 |
| R4 | Lifecycle & config refresh | Settings cached globally; scheduler/AI/OCR use synchronous DB/HTTP without circuit breakers; config rotation may lag up to TTL. | Medium | Medium | P0 | Remove exported global settings, rely solely on get_settings per call or reduce TTL; add heartbeat failure handling and timeouts/metrics around external calls.【F:app/config.py†L96-L132】【F:app/services/ai_proof_advisor.py†L259-L292】 |
| R5 | AI/OCR privacy | Allowlist/redaction may omit unanticipated sensitive keys; backend_checks/mandate_context partially masked only. | High | Medium | P0 | Expand allowlist tests (IBAN/email/phone/custom keys), enforce redaction for unknown metadata before OpenAI call, and log dropped keys for tuning.【F:app/services/ai_proof_advisor.py†L215-L236】【F:app/utils/masking.py†L112-L169】 |
| R6 | Observability | No metrics/tracing; health relies on DB access and hardcoded migration id; lacks readiness for external dependencies. | Medium | Medium | P1 | Add metrics for AI/OCR/PSP outcomes, dynamic migration head lookup, and graceful degraded health states.【F:app/routers/health.py†L20-L106】 |

## I. AI Proof Advisor, OCR & risk scoring (dedicated section)
### I.1 AI architecture
- Config flags in `Settings`: AI_PROOF_ADVISOR_ENABLED (False by default), provider/model/timeout, OpenAI key; OCR flags/provider/api key likewise default to disabled/none.【F:app/config.py†L54-L68】
- Modules: AI Proof Advisor builds prompts, sanitizes context, and handles fallbacks; masking utilities for metadata; invoice OCR normalizer/stub; document backend checks for comparisons.【F:app/services/ai_proof_advisor.py†L251-L292】【F:app/utils/masking.py†L112-L169】【F:app/services/invoice_ocr.py†L39-L163】【F:app/services/document_checks.py†L1-L170】

### I.2 AI integration into proof flows
- Photo proofs: AI advisory runs only after validations when enabled; result stored in metadata without blocking approval; invoice totals/currency passed from normalized helper.【F:app/services/proofs.py†L181-L219】
- Document proofs: OCR enriches metadata, normalization computes typed amounts/currency, backend checks computed, AI advisory consumes sanitized metadata and stores assessment; decisions remain manual.【F:app/services/proofs.py†L93-L219】
- AI outputs persisted in read-only model fields and surfaced via ProofRead; clients cannot write them.【F:app/models/proof.py†L39-L46】【F:app/schemas/proof.py†L29-L39】

### I.3 OCR & backend_checks
- OCR toggle/provider pulled from settings; provider `none` returns `{}` without failure; normalization maps totals/currency/date/supplier/IBAN last4/masked and sets ocr_status/provider flags without overwriting user data.【F:app/services/invoice_ocr.py†L17-L163】
- Backend checks compare proof_requirements vs metadata (amount, IBAN, dates, supplier) returning structured flags for AI context; missing data handled gracefully.【F:app/services/document_checks.py†L36-L170】

### I.4 AI/OCR-specific risks
| ID | Domain (AI/OCR) | Risk | Impact | Likelihood | Priority | Recommended fix |
| --- | --- | --- | --- | --- | --- | --- |
| AI1 | Privacy | Unknown metadata keys dropped instead of explicitly redacted; sensitive keys outside allowlist could be forwarded if added elsewhere. | High | Medium | P0 | Enforce default redaction for non-allowlisted keys and add regression tests for IBAN/email/phone/custom fields.【F:app/services/ai_proof_advisor.py†L215-L236】【F:app/utils/masking.py†L112-L169】 |
| AI2 | Resilience | AI call synchronous with limited timeout; lacks metrics/retries; failures only logged. | Medium | Medium | P0 | Add metrics and configurable retries/circuit breaker; consider background processing for AI scoring.【F:app/services/ai_proof_advisor.py†L259-L292】 |
| AI3 | Data consistency | Normalization quietly returns None on parse errors; AI context may omit financial data while metadata still contains raw strings. | High | Medium | P0 | Raise validation or mark normalization errors in metadata/audit; ensure AI context gets deterministic placeholders/tests.【F:app/services/invoice_ocr.py†L102-L129】 |
| AI4 | Auditability | AI/OCR operations not inserted into AuditLog; forensic trace of automated assessments missing. | Medium | Medium | P1 | Add AuditLog entries for AI/OCR invocations with sanitized payload and outcome status.【F:app/services/proofs.py†L86-L219】 |
| AI5 | Provider integration | OCR provider stub only; switching to real provider may lack error handling/contracts. | Medium | Low | P2 | Implement provider adapters with strict schema validation and contract tests before production enablement.【F:app/services/invoice_ocr.py†L23-L37】 |

## J. Roadmap to a staging-ready MVP
- P0 checklist (blocking):
  - Enforce mandatory PSP webhook secrets in non-dev, shrink timestamp drift, and add nonce cache/metrics to complement event_id uniqueness for replay defense.【F:app/routers/psp.py†L29-L48】【F:app/services/psp_webhooks.py†L68-L132】
  - Harden AI masking: default redaction for unknown keys, expand tests for PII patterns, and surface dropped keys for tuning before OpenAI calls.【F:app/services/ai_proof_advisor.py†L215-L236】【F:app/utils/masking.py†L112-L169】
  - Elevate monetary normalization: validate/flag invalid currency/amount inputs instead of silently coercing to None; audit normalization failures.【F:app/services/invoice_ocr.py†L102-L129】
  - Add AuditLog entries for AI/OCR execution and successful payment settlements to complete lifecycle forensics.【F:app/services/proofs.py†L86-L219】【F:app/services/psp_webhooks.py†L138-L205】
  - Strengthen lifecycle/health: remove global settings cache export, ensure config refresh, and add metrics/alerts for scheduler lock staleness and DB health.【F:app/config.py†L96-L132】【F:app/services/scheduler_lock.py†L18-L154】【F:app/routers/health.py†L49-L106】
- P1 checklist (pre-pilot):
  - Add metrics/tracing for AI/OCR/PSP outcomes and webhook failure rates; dynamic Alembic head detection instead of hardcoded revision.
  - Pagination/search for user/proof/transaction lists; stricter validators on geofence/doc fields.
  - Background or async AI/OCR execution with timeouts to reduce request latency.
- P2 checklist (comfort/scalability):
  - Circuit breakers and retries for external providers; correlation IDs in logs; configurable scheduler lock names per environment.
  - Documentation of data retention/privacy posture for AI/OCR payloads.

- **Verdict: NO-GO for staging with 10 real users** until P0 items (PSP secret enforcement/nonce cache, AI masking/validation, monetary normalization visibility, and full audit coverage) are addressed and validated by targeted tests.

## K. Verification evidence
- Migrations (conceptual): `alembic current/heads/history --verbose` would confirm head `4e1bd5489e1c` with scheduler lock owner/expiry and presence of PSP webhook events/proof AI fields from initial schema (not executed; inferred from files).【F:alembic/versions/4e1bd5489e1c_add_owner_and_expires_to_scheduler_locks.py†L1-L31】【F:alembic/versions/baa4932d9a29_0001_init_schema.py†L31-L46】
- Tests (conceptual): `pytest -q` would exercise health telemetry, AI privacy, OCR normalization, PSP signature/replay handling, scheduler lock behavior, escrow/proof/payment flows, and transaction audits based on test suite layout (not executed in this audit).
- Code anchors: Proof lifecycle, AI/OCR integration, masking, normalization, PSP verification, and health telemetry referenced throughout this report.【F:app/services/proofs.py†L86-L219】【F:app/services/ai_proof_advisor.py†L215-L292】【F:app/utils/masking.py†L112-L169】【F:app/services/invoice_ocr.py†L102-L163】【F:app/services/psp_webhooks.py†L68-L205】【F:app/routers/health.py†L20-L106】【F:app/services/scheduler_lock.py†L18-L154】
