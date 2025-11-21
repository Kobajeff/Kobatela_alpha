# Kobatela_alpha — Capability & Stability Audit (2025-11-21)

## A. Executive summary
- Comprehensive FastAPI surface covering escrows, proofs, payments, spend controls, alerts, public mandates, and health with scoped API-key auth and audit logs on key actions. 【F:app/routers/escrow.py†L21-L107】【F:app/security.py†L33-L183】【F:app/routers/health.py†L104-L142】
- AI Proof Advisor and invoice OCR are feature-flagged off by default, with nullable AI columns and masking helpers to protect sensitive metadata before provider calls. 【F:app/config.py†L54-L68】【F:app/models/proof.py†L39-L49】【F:app/services/ai_proof_advisor.py†L277-L333】【F:app/utils/masking.py†L66-L132】
- Proof flow includes EXIF/geofence validation, invoice normalization, AI advisory (non-blocking), backend document checks, and audit logging for OCR/AI events. 【F:app/services/proofs.py†L87-L197】【F:app/services/proofs.py†L329-L381】【F:app/services/document_checks.py†L36-L170】【F:app/services/invoice_ocr.py†L274-L305】
- PSP webhook processing verifies HMAC/timestamp drift and deduplicates events; payments include idempotency keys for payouts. 【F:app/services/psp_webhooks.py†L100-L191】【F:app/services/proofs.py†L417-L436】【F:app/services/proofs.py†L560-L568】
- Rich test suite (static review) covers AI flags/privacy/resilience, OCR normalization, EXIF/geofence rules, spend idempotency, PSP webhooks, scheduler locks, and health telemetry. 【F:tests/test_ai_config.py†L1-L73】【F:tests/test_ai_resilience.py†L1-L140】【F:tests/test_invoice_ocr.py†L1-L140】【F:tests/test_milestone_sequence_and_exif.py†L1-L160】【F:tests/test_psp_webhook.py†L1-L200】【F:tests/test_scheduler_lock.py†L1-L120】

Major risks / limitations:
- Geofence latitude/longitude/radius use `Float`, risking precision drift for distance validation and geofence-based approvals. 【F:app/models/milestone.py†L56-L59】【F:app/services/proofs.py†L137-L180】
- Invoice normalization raises hard 422 errors and OCR is invoked with empty bytes synchronously; enabling a real provider could add latency or fail without retries. 【F:app/services/proofs.py†L87-L120】【F:app/services/invoice_ocr.py†L179-L218】
- AI circuit breaker and counters are in-memory per process; enabling AI without an API key returns fallback but still increments error counters and hides persistent failure visibility. 【F:app/services/ai_proof_advisor.py†L23-L92】【F:app/services/ai_proof_advisor.py†L436-L496】
- Settings cache TTL is 60s, which can delay PSP secret rotations or AI/OCR flag changes; webhook drift window fixed at 180s in config and 300s in `.env.example`. 【F:app/config.py†L96-L116】【F:.env.example†L4-L8】
- No commands (tests/migrations) executed in this audit; runtime stability is inferred only from static analysis and test intent. 

Readiness score (staging MVP): **76 / 100** — strong functional surface and guardrails, but P0 items (monetary precision for geofence, webhook hardening, AI/OCR resilience) must be addressed before exposing to real users.

## B. Capability map (current features)
### B.1 Functional coverage
| Feature | Endpoints / modules involved | Status (OK / Partial / Missing) | Notes |
| --- | --- | --- | --- |
| Health & runtime introspection | `/health` | OK | Reports DB connectivity, alembic head vs current, scheduler state, PSP secret fingerprints, AI/OCR flags. 【F:app/routers/health.py†L104-L142】 |
| User & API key management | `/users`, `/apikeys` | Partial | CRUD endpoints and audit on key use; pagination/search depth unclear. 【F:app/routers/users.py†L16-L98】【F:app/routers/apikeys.py†L37-L116】 |
| Escrow lifecycle | `/escrows/*` | OK | Create, deposit (idempotency key), delivered, client approve/reject, deadline check, read with audit. 【F:app/routers/escrow.py†L21-L107】 |
| Proof submission & decision | `/proofs` | OK | EXIF/geofence validation, invoice normalization, OCR enrichment, AI advisory, auto-approve path, manual decisions with AI note guard. 【F:app/routers/proofs.py†L24-L54】【F:app/services/proofs.py†L67-L515】 |
| Payments & PSP webhook | `/payments/execute/{id}`, `/psp/webhook` | OK | Manual payout execution and webhook HMAC/timestamp verification with replay defense. 【F:app/routers/payments.py†L18-L63】【F:app/services/psp_webhooks.py†L100-L191】 |
| Spend controls & transactions | `/spend/*`, `/transactions` | OK | Merchants, allowlist, purchases with idempotency, admin transactions. 【F:app/routers/spend.py†L21-L116】【F:app/routers/transactions.py†L21-L86】 |
| Alerts & public mandates | `/alerts`, `/kct_public/*` | OK | Alert listing and GOV/ONG public sector aggregation. 【F:app/routers/alerts.py†L7-L40】【F:app/routers/kct_public.py†L21-L163】 |
| AI & OCR toggles | `ai_proof_flags`, `invoice_ocr` | Partial | Feature-flagged and masked; OCR provider stub only, AI breaker local. 【F:app/services/ai_proof_flags.py†L10-L31】【F:app/services/invoice_ocr.py†L179-L218】【F:app/services/ai_proof_advisor.py†L23-L92】 |
| Scheduler | Lifespan + DB lock | OK | Optional scheduler with lock heartbeat and release. 【F:app/main.py†L64-L134】【F:app/services/scheduler_lock.py†L36-L116】 |

### B.2 End-to-end journeys supported today
- Photo proof: submit with EXIF/geofence validation → optional AI advisory → auto-approve if clean → payout with idempotency and audit logs. 【F:app/services/proofs.py†L137-L455】
- Invoice/contract proof: submit → OCR enrichment + normalization → backend checks → AI advisory for manual review → AI fields persisted with audit. 【F:app/services/proofs.py†L83-L381】【F:app/services/document_checks.py†L36-L170】
- PSP settlement: webhook verifies signature/timestamp and deduplicates event IDs before updating payment status. 【F:app/services/psp_webhooks.py†L100-L191】
- Spend/transaction controls: allowlists, merchants, purchases, and transactions with idempotency keys and scoped access. 【F:app/routers/spend.py†L21-L116】【F:app/routers/transactions.py†L21-L86】
- Scheduler safety: lifespan hook acquires/refreshes DB lock; helper manages heartbeat and release. 【F:app/main.py†L64-L134】【F:app/services/scheduler_lock.py†L36-L116】

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
| GET | `/alerts` | `alerts.list_alerts` | API key | admin/support | query `type` | list[`AlertRead`] | 200 |
| GET | `/kct_public/mandates` | `kct_public.list_public_mandates` | API key | GOV/ONG | query filters | list[`PublicMandateRead`] | 200 |

## D. Data model & state machines
- Entities:
  - Proof: sha256-unique proofs with metadata JSON, normalized invoice fields, AI assessment columns (risk level/score/flags/explanation/checked_at/reviewed_by/at). 【F:app/models/proof.py†L11-L49】
  - Milestone: per-escrow unique idx, `Numeric(18,2)` amount, proof_requirements JSON, geofence lat/lng/radius as `Float`, status enum. 【F:app/models/milestone.py†L32-L62】
  - EscrowAgreement/Deposit/Event: statuses, deadlines, positive deposit amounts with idempotency key in service layer. 【F:app/models/escrow.py†L12-L55】【F:app/services/escrow.py†L67-L154】
  - Payment: numeric amount, unique PSP reference/idempotency keys, status enum. 【F:app/models/payment.py†L16-L38】【F:app/services/payments.py†L23-L86】
  - API Key: scoped tokens with unique hash/prefix; audit on use. 【F:app/models/api_key.py†L11-L32】【F:app/security.py†L33-L133】
  - AuditLog: actor/action/entity/data_json/at for immutable audit trail. 【F:app/models/audit.py†L8-L17】
  - SchedulerLock: owner/expires_at indexed for lock heartbeat. 【F:app/models/scheduler_lock.py†L11-L24】
- State machines:
  - Proof: WAITING milestone → submit sets proof to PENDING or APPROVED (photo auto-approve) → decision approve/reject adjusts milestone status and AI review markers; approvals trigger payout. 【F:app/services/proofs.py†L126-L355】【F:app/services/proofs.py†L458-L589】
  - Escrow: statuses enumerated with deposit events and deadline checks driving release/refund flows. 【F:app/models/escrow.py†L12-L46】【F:app/services/escrow.py†L67-L154】
  - Payment: PENDING → SENT/SETTLED/ERROR/REFUNDED via manual execution or PSP webhook updates. 【F:app/models/payment.py†L16-L30】【F:app/services/psp_webhooks.py†L164-L228】

## E. Stability results
- Static view of tests (not executed): suite covers AI config/privacy/resilience (`test_ai_config.py`, `test_ai_privacy.py`, `test_ai_resilience.py`), OCR normalization (`test_invoice_ocr.py`, `test_invoice_ocr_contract.py`), proof EXIF/geofence and AI review (`test_milestone_sequence_and_exif.py`, `test_proof_ai_review.py`), spend idempotency (`test_spend_idempotency.py`, `test_usage_spend.py`), PSP webhook signing (`test_psp_webhook.py`), scheduler lock and flag (`test_scheduler_lock.py`, `test_scheduler_flag.py`), health/observability (`test_health.py`, `test_observability.py`), and table existence (`tests/check_tables.py`, `tests/test_tables.py`). 【F:tests/test_ai_config.py†L1-L73】【F:tests/test_invoice_ocr.py†L1-L140】【F:tests/test_psp_webhook.py†L1-L200】【F:tests/test_scheduler_lock.py†L1-L120】【F:tests/test_spend_idempotency.py†L1-L140】
- No tests or migrations were run in this audit (static analysis only). Runtime stability is inferred from code paths and test intent.
- Static review notes: geofence math uses floats; AI/OCR calls are guarded by try/except but OCR invoked with empty bytes; settings cache may stale; over-broad exceptions exist around AI/OCR calls (intentional to avoid blocking). 【F:app/services/proofs.py†L137-L180】【F:app/services/invoice_ocr.py†L179-L218】【F:app/config.py†L96-L116】【F:app/services/ai_proof_advisor.py†L436-L496】

## F. Security & integrity
- AuthN/Z: API key validation with scopes (sender/support/admin) and optional legacy dev key; GOV/ONG restriction for public endpoints. 【F:app/security.py†L33-L183】【F:app/routers/kct_public.py†L21-L84】
- Input validation: Pydantic schemas enforce types for proofs, escrows, spend, payments; numeric fields use Decimal/Numeric except geofence floats. 【F:app/schemas/proof.py†L5-L38】【F:app/schemas/escrow.py†L5-L64】【F:app/models/milestone.py†L32-L62】
- File/proof validation: SHA256 uniqueness, EXIF/geofence checks, hard validation errors raise 422, manual review path for soft errors, AI advisory non-blocking. 【F:app/models/proof.py†L22-L36】【F:app/services/proofs.py†L137-L197】【F:app/services/proofs.py†L201-L290】
- Secrets & config: Settings via `.env`, feature flags for AI/OCR, PSP webhook secrets with optional rotation and drift window; cache TTL 60s. 【F:app/config.py†L35-L116】【F:.env.example†L1-L25】
- Audit/logging: AuditLog rows added for proof submission/decision, OCR run, AI assessments, API key use; logging in AI/OCR and proofs. 【F:app/services/proofs.py†L329-L404】【F:app/services/proofs.py†L358-L381】【F:app/security.py†L53-L133】【F:app/services/invoice_ocr.py†L296-L305】【F:app/services/ai_proof_advisor.py†L499-L507】

## G. Observability & operations
- Logging: module-level loggers across services; AI/OCR and proof flows log warnings/errors and durations; no correlation IDs. 【F:app/services/ai_proof_advisor.py†L436-L507】【F:app/services/invoice_ocr.py†L296-L305】【F:app/services/proofs.py†L417-L453】
- HTTP error handling: consistent `HTTPException` usage with structured error codes for validation/state errors; PSP webhook returns 4xx/5xx on signature/drift/provider issues. 【F:app/services/proofs.py†L72-L197】【F:app/services/psp_webhooks.py†L100-L191】
- Alembic migrations health: migrations add AI/OCR and scheduler fields; health endpoint compares DB head with expected and exposes migration drift. 【F:alembic/versions/c6f0c1c0b8f4_add_invoice_fields_to_proofs.py†L14-L35】【F:alembic/versions/c7f3d2f1fb35_change_ai_score_to_numeric.py†L17-L32】【F:app/routers/health.py†L64-L99】
- Deployment specifics: optional scheduler via env flag with DB lock TTL; settings TTL may mask env changes for up to 60s; no command outputs (tests/migrations) executed here. 【F:app/main.py†L64-L134】【F:app/config.py†L96-L116】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority (P0/P1/P2) | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Monetary/geofence precision | Geofence lat/lng/radius stored as `Float`, distance check uses math floats → possible false positives/negatives for proof validation. 【F:app/models/milestone.py†L56-L59】【F:app/services/proofs.py†L137-L180】 | Medium | Medium | P0 | Migrate geofence fields to `Numeric(9,6, asdecimal=True)` with Decimal-based haversine; add Alembic migration and unit tests. Effort: ~0.5 day. |
| R2 | PSP webhook secret freshness | Secrets cached 60s; drift window fixed; potential replay/rotation lag. 【F:app/config.py†L96-L116】【F:app/services/psp_webhooks.py†L100-L171】 | High | Low | P0 | Bypass cache for webhook path or reduce TTL to ~5s; enforce secret presence in non-dev and persist replay IDs with expiry. Effort: ~0.5 day. |
| R3 | Business lifecycle audit | Escrow transitions lack dedicated audit entries (except read); scheduler lock changes not audited. 【F:app/routers/escrow.py†L45-L86】【F:app/services/scheduler_lock.py†L36-L116】 | Medium | Medium | P0 | Add AuditLog on delivered/approve/reject/deadline actions and scheduler acquire/refresh/release; expose audit export. Effort: ~0.5 day. |
| R4 | FastAPI lifespan robustness | Scheduler lock tied to lifespan; failure during shutdown may leave stale lock and no per-worker health. 【F:app/main.py†L64-L134】 | Medium | Low | P0 | Add try/finally for lock release, heartbeat failure alerts, and document single-runner constraint. Effort: ~0.5 day. |
| R5 | AI & OCR safety defaults | AI breaker/counters in-memory; AI enabled without key returns fallback; OCR called with empty bytes; masking allowlist may miss fields. 【F:app/services/ai_proof_advisor.py†L23-L92】【F:app/services/ai_proof_advisor.py†L436-L496】【F:app/services/proofs.py†L87-L99】【F:app/utils/masking.py†L66-L132】 | High | Medium | P0 | Persist breaker metrics (DB/Redis), expose in health, fail fast when AI enabled without key, skip OCR when no file, enforce allowlist masking; add tests. Effort: ~1 day. |
| R6 | Invoice normalization hardness | Hard 422 on normalization error blocks submission without user guidance. 【F:app/services/proofs.py†L102-L120】 | Medium | Medium | P1 | Treat normalization errors as soft/manual review with audit flag, or return actionable error codes; add retries or client hints. Effort: ~0.5 day. |
| R7 | OCR performance | OCR synchronous call may block request thread if real provider used. 【F:app/services/invoice_ocr.py†L179-L218】 | Medium | Low | P2 | Offload to background task/worker or async, add timeout and payload size checks. Effort: ~1 day. |
| R8 | Idempotency reuse | Idempotency helpers duplicated across routers; risk of inconsistencies. 【F:app/services/idempotency.py†L1-L85】【F:app/routers/transactions.py†L46-L68】 | Low | Medium | P2 | Centralize dependency and add cross-route tests for duplicate keys. Effort: ~0.5 day. |

## I. AI Proof Advisor, OCR & risk scoring (dedicated section)
### I.1 AI architecture
- Config defaults: AI disabled by default with provider/model/timeout, OpenAI key optional; OCR disabled with provider "none". 【F:app/config.py†L54-L68】【F:.env.example†L10-L25】
- Modules: feature flags (`ai_proof_flags`), advisory service with masking/circuit breaker (`ai_proof_advisor`), backend checks (`document_checks`), OCR normalization/enrichment (`invoice_ocr`). 【F:app/services/ai_proof_flags.py†L10-L31】【F:app/services/ai_proof_advisor.py†L23-L507】【F:app/services/document_checks.py†L36-L170】【F:app/services/invoice_ocr.py†L179-L305】

### I.2 AI integration into proof flows
- PHOTO proofs: after EXIF/geofence validation, AI (if enabled) builds mandate/backend/document context, masks sensitive fields, and stores `ai_assessment` plus AI columns; failures logged and non-blocking. 【F:app/services/proofs.py†L137-L244】【F:app/services/ai_proof_advisor.py†L277-L333】【F:app/services/proofs.py†L329-L355】
- NON-PHOTO proofs (PDF/INVOICE/CONTRACT): always manual review; computes backend checks and passes to AI; stores AI assessment and columns; AI failures logged without blocking. 【F:app/services/proofs.py†L245-L355】【F:app/services/document_checks.py†L36-L170】
- Storage: AI fields set on Proof (risk level/score/flags/explanation/checked_at/reviewed_by/at) and audit entries for AI/OCR runs. 【F:app/models/proof.py†L39-L49】【F:app/services/proofs.py†L329-L381】【F:app/services/proofs.py†L458-L513】
- Guarantees: AI optional via `AI_PROOF_ADVISOR_ENABLED`; missing API key returns fallback; AI exceptions caught to avoid 5xx; masking removes sensitive patterns before provider call. 【F:app/services/ai_proof_flags.py†L10-L19】【F:app/services/ai_proof_advisor.py†L436-L496】【F:app/utils/masking.py†L66-L132】

### I.3 OCR & backend_checks
- OCR enrichment: `run_invoice_ocr_if_enabled` respects feature flag/provider, normalizes via Pydantic, returns disabled/error structures; `enrich_metadata_with_invoice_ocr` avoids overwriting existing metadata and logs status. 【F:app/services/invoice_ocr.py†L179-L218】【F:app/services/invoice_ocr.py†L274-L305】
- Backend checks: `compute_document_backend_checks` compares expected amount/currency/IBAN/date/supplier with metadata, returning structured signals without raising. 【F:app/services/document_checks.py†L36-L170】
- Integration: submit_proof calls OCR/normalization before backend checks; backend checks injected into AI context for non-photo proofs. 【F:app/services/proofs.py†L87-L123】【F:app/services/proofs.py†L245-L285】

### I.4 AI/OCR-specific risks
| ID | Domain (AI/OCR) | Risk | Impact | Likelihood | Priority | Recommended fix |
| --- | --- | --- | --- | --- | --- | --- |
| AI1 | Circuit breaker locality | Per-process counters allow AI thrash across workers; no health exposure. 【F:app/services/ai_proof_advisor.py†L23-L92】 | Medium | Medium | P0 | Persist counters/metrics centrally and expose in `/health`. |
| AI2 | Missing API key tolerance | AI enabled without `OPENAI_API_KEY` returns fallback but increments errors silently. 【F:app/services/ai_proof_advisor.py†L456-L470】 | Medium | Medium | P0 | Fail fast at startup or auto-disable with audit log when key missing. |
| AI3 | Masking coverage | Pattern-based masking might miss new sensitive fields (e.g., supplier address). 【F:app/utils/masking.py†L66-L132】 | High | Medium | P0 | Switch to allowlist-based masking and add unit tests for new fields. |
| AI4 | OCR invocation without content | OCR called with empty bytes; real provider may error/slow. 【F:app/services/proofs.py†L87-L99】【F:app/services/invoice_ocr.py†L179-L218】 | Medium | Medium | P1 | Skip OCR when file bytes absent; add timeout and async worker. |
| AI5 | AI field governance | AI fields are read-only to clients but rely on model defaults; ensure migrations align and add tests. 【F:app/models/proof.py†L39-L49】【F:app/schemas/proof.py†L5-L38】 | Medium | Low | P2 | Add schema tests and DB defaults/nullability checks. |

## J. Roadmap to a staging-ready MVP
- P0 checklist (blocking):
  - Migrate geofence floats to Decimal/Numeric and update haversine to Decimal math; add migration and tests. 【F:app/models/milestone.py†L56-L59】【F:app/services/proofs.py†L137-L180】
  - Harden PSP webhook: reduce settings cache TTL or bypass for webhook path, enforce secret presence, tune drift window, persist replay IDs. 【F:app/config.py†L96-L116】【F:app/services/psp_webhooks.py†L100-L191】
  - Centralize AI breaker/metrics, expose in health, fail fast when AI enabled without key, and enhance masking allowlist; skip OCR when no file bytes. 【F:app/services/ai_proof_advisor.py†L23-L92】【F:app/services/ai_proof_advisor.py†L436-L496】【F:app/utils/masking.py†L66-L132】【F:app/services/proofs.py†L87-L99】
  - Add audit logs for escrow lifecycle transitions and scheduler lock operations. 【F:app/routers/escrow.py†L45-L86】【F:app/services/scheduler_lock.py†L36-L116】
- P1 checklist (pre-pilot):
  - Make invoice normalization failures soft/manual-review with explicit codes; add client guidance and retries. 【F:app/services/proofs.py†L102-L120】
  - Move OCR to background worker/async and enforce timeouts/payload limits. 【F:app/services/invoice_ocr.py†L179-L218】
  - Strengthen health endpoint with AI breaker state, OCR/AI counters, and scheduler lock age. 【F:app/services/ai_proof_advisor.py†L82-L92】【F:app/routers/health.py†L104-L142】
- P2 checklist (comfort/scalability):
  - Refactor idempotency dependencies for reuse across spend/transactions/payments; add pagination to user/API key listings. 【F:app/routers/transactions.py†L46-L68】【F:app/routers/spend.py†L55-L95】【F:app/routers/users.py†L16-L98】
  - Add structured logging with correlation IDs and optional Sentry/Prometheus wiring. 【F:app/config.py†L51-L53】

**Verdict: NO-GO for a staging with 10 real users until P0 items (geofence precision, webhook hardening, AI breaker persistence/masking, lifecycle audit logs) are fixed.**

## K. Verification evidence
- Migrations (conceptual, not run): `alembic current`, `alembic heads`, `alembic history --verbose` would confirm alignment of invoice fields, AI numeric score, scheduler locks, and AI review columns with migrations. 【F:alembic/versions/c6f0c1c0b8f4_add_invoice_fields_to_proofs.py†L14-L35】【F:alembic/versions/c7f3d2f1fb35_change_ai_score_to_numeric.py†L17-L32】【F:alembic/versions/1b7cc2cfcc6e_add_ai_review_fields_to_proofs.py†L17-L45】【F:app/routers/health.py†L64-L99】
- Tests (conceptual, not run): `pytest -q` would execute AI/OCR, proofs, spend, PSP webhook, scheduler, health, and audit sanitization suites listed in section E to validate behaviors. 【F:tests/test_ai_resilience.py†L1-L140】【F:tests/test_invoice_ocr.py†L1-L140】【F:tests/test_psp_webhook.py†L1-L200】【F:tests/test_scheduler_lock.py†L1-L120】【F:tests/test_audit_sanitization.py†L1-L140】
- Key code references: routers, services, models, and migrations cited above demonstrate endpoints, AI/OCR integration, monetary handling, and security policies. 【F:app/services/proofs.py†L67-L589】【F:app/services/ai_proof_advisor.py†L277-L507】【F:app/services/invoice_ocr.py†L179-L305】【F:app/security.py†L33-L183】
