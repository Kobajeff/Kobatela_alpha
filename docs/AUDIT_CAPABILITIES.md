# Kobatela_alpha — Capability & Stability Audit (2025-11-21)

## A. Executive summary
- Escrow, spend, PSP, and proof flows are fully routed with API-key scopes, idempotency guards on monetary writes, and audited decisions, giving deterministic lifecycle control. 【F:app/routers/escrow.py†L21-L86】【F:app/routers/spend.py†L21-L116】【F:app/routers/psp.py†L17-L67】【F:app/services/proofs.py†L292-L356】
- AI Proof Advisor and invoice OCR are feature-flagged off by default, fall back safely when disabled/misconfigured, and mask metadata before any AI call. 【F:app/config.py†L54-L68】【F:.env.example†L10-L25】【F:app/services/ai_proof_advisor.py†L196-L247】【F:app/utils/masking.py†L66-L132】
- Proof ingestion normalizes invoice amounts/currency, enriches metadata with OCR (non-overwriting), and persists AI advisory outputs into dedicated columns plus audit logs. 【F:app/services/proofs.py†L83-L120】【F:app/services/invoice_ocr.py†L274-L305】【F:app/models/proof.py†L22-L47】
- PSP webhook processing enforces HMAC+timestamp, rejects replays, and requires configured secrets with status surfacing in `/health`. 【F:app/services/psp_webhooks.py†L100-L190】【F:app/routers/health.py†L20-L109】
- Observability includes structured health payload (DB/migrations/AI/OCR/scheduler), audit logs for key actions, and scheduler lock diagnostics. 【F:app/routers/health.py†L20-L109】【F:app/models/audit.py†L8-L17】【F:app/services/scheduler_lock.py†L36-L116】

Major risks / limitations:
- Monetary geofence fields use floating point; invoice normalization 422s can block submissions without retry guidance. 【F:app/models/milestone.py†L32-L52】【F:app/services/proofs.py†L102-L120】
- AI circuit breaker is in-memory only and resets per process; AI results stored as Decimal but migration history includes Float remnants. 【F:app/services/ai_proof_advisor.py†L15-L61】【F:alembic/versions/013024e16da9_add_ai_fields_to_proofs.py†L14-L34】【F:alembic/versions/c7f3d2f1fb35_change_ai_score_to_numeric.py†L14-L24】
- Settings cache TTL (60s) may delay rotation of PSP secrets or AI/OCR flags; legacy dev key accepted when ENV allows. 【F:app/config.py†L96-L133】【F:app/security.py†L13-L77】
- OCR stub runs even without file bytes (b"") and AI/OCR errors only logged; synchronous calls could slow proof submission. 【F:app/services/proofs.py†L87-L120】【F:app/services/invoice_ocr.py†L179-L217】
- Tests/migrations not executed in this audit; stability conclusions are static only.

Readiness score (staging MVP): **80 / 100** — Solid route coverage and guards exist; tighten monetary precision, AI resilience, and secret/flag refresh before onboarding real users.

## B. Capability map (current features)
### B.1 Functional coverage
| Feature | Endpoints / modules involved | Status (OK / Partial / Missing) | Notes |
| --- | --- | --- | --- |
| Health & runtime introspection | `/health` | OK | Reports PSP secret status/fingerprints, AI/OCR toggles, DB/migration status, scheduler lock description. 【F:app/routers/health.py†L20-L109】 |
| User & API key lifecycle | `/users`, `/apikeys` | Partial | Admin/support CRUD and audit on use; no pagination/search depth shown. 【F:app/routers/users.py†L1-L55】【F:app/routers/apikeys.py†L37-L116】 |
| Escrow lifecycle | `/escrows/*` | OK | Create/deposit/mark-delivered/approve/reject/deadline check with audit on reads and idempotent deposits. 【F:app/routers/escrow.py†L21-L86】 |
| Proof submission & decision | `/proofs` | OK | EXIF/geofence validation, OCR enrichment, normalization + AI advisory, manual decision with AI note guard and audits. 【F:app/services/proofs.py†L67-L513】【F:app/routers/proofs.py†L20-L48】 |
| Payments & PSP integration | `/payments/execute/{id}`, `/psp/webhook` | OK | Manual execution plus HMAC/timestamp verification, event_id replay defense, settlement/error handling with auditing. 【F:app/routers/psp.py†L17-L67】【F:app/services/psp_webhooks.py†L100-L228】 |
| Transactions & spend controls | `/spend/*`, `/transactions` | OK | Allowlist/categories/merchants/purchases with idempotency and admin transaction CRUD plus audited reads. 【F:app/routers/transactions.py†L21-L86】【F:app/routers/spend.py†L21-L116】 |
| AI & OCR toggles | `ai_proof_flags`, `invoice_ocr` | Partial | Flags present; OCR provider is dummy-only; AI circuit breaker in-memory. 【F:app/services/ai_proof_flags.py†L5-L22】【F:app/services/invoice_ocr.py†L179-L217】 |
| Scheduler | Lifespan + DB lock | OK | Owner+TTL lock with refresh/release and health description; single-runner APScheduler design. 【F:app/services/scheduler_lock.py†L36-L116】【F:app/main.py†L64-L134】 |

### B.2 End-to-end journeys supported today
- Photo proof: submit → EXIF/geofence validation → optional AI advisory → auto-approve if validations pass → payout execution with idempotent keying and audits. 【F:app/services/proofs.py†L126-L454】
- Invoice/contract proof: submit → OCR enrichment → normalization → backend checks → AI advisory (manual review) → AI fields/metadata persisted with audits. 【F:app/services/proofs.py†L83-L380】
- PSP settlement: webhook verifies signature/timestamp, deduplicates event_id, and settles/errors payments; failures audited. 【F:app/services/psp_webhooks.py†L100-L228】
- Spend/transaction control: allowlist/categories/merchants plus purchases/transactions with idempotency and admin scopes, audited on reads. 【F:app/routers/transactions.py†L21-L86】【F:app/routers/spend.py†L21-L116】
- Scheduler housekeeping: DB lock acquisition/refresh/release with TTL and health visibility for multi-runner safety. 【F:app/services/scheduler_lock.py†L36-L116】【F:app/routers/health.py†L87-L109】

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

## D. Data model & state machines
- Entities:
  - Proof: unique sha256, JSON metadata, invoice_total_amount Numeric(18,2), invoice_currency String(3), AI advisory fields (risk level/score/flags/explanation/timestamps/reviewer). 【F:app/models/proof.py†L12-L47】
  - EscrowAgreement/Deposit/Event: Numeric totals with status enum, deadline, release conditions, positive deposit amounts, and idempotent deposit key. 【F:app/models/escrow.py†L12-L51】
  - Milestone: per-escrow unique idx with amount Numeric(18,2), proof_requirements JSON, geofence floats, status enum driving proof gating. 【F:app/models/milestone.py†L16-L55】
  - Payment: Numeric amount, unique psp_ref/idempotency_key, status enum with positive-amount constraint. 【F:app/models/payment.py†L16-L38】
  - Transactions/Spend: allowlists, merchants, allowed payees, purchases with Decimal amounts and idempotency keys (see spend/transactions routers for flows). 【F:app/routers/spend.py†L21-L116】【F:app/routers/transactions.py†L21-L86】
  - API keys: scoped tokens with unique hash/prefix and audit on use. 【F:app/models/api_key.py†L11-L32】【F:app/security.py†L13-L77】
  - AuditLog: actor/action/entity/data_json/at fields for lifecycle traces. 【F:app/models/audit.py†L8-L17】
  - SchedulerLock: owner, expires_at with indexes and TTL management. 【F:app/models/scheduler_lock.py†L11-L24】
- State machines:
  - Proof: WAITING milestone → submit sets proof PENDING or APPROVED (photo auto-approve) → decision approve/reject updates milestone and AI review markers; approvals trigger payout with idempotency key. 【F:app/services/proofs.py†L126-L454】【F:app/services/proofs.py†L458-L513】
  - Escrow: statuses enumerated (DRAFT/FUNDED/RELEASABLE/RELEASED/REFUNDED/CANCELLED); events logged via EscrowEvent, deposits tracked idempotently. 【F:app/models/escrow.py†L8-L46】
  - Payment: PENDING→SENT/SETTLED/ERROR/REFUNDED; PSP webhooks finalize settlement with replay protection. 【F:app/models/payment.py†L16-L30】【F:app/services/psp_webhooks.py†L174-L228】
  - Scheduler lock: acquire → refresh heartbeat → release on shutdown; prevents concurrent schedulers. 【F:app/services/scheduler_lock.py†L36-L116】

## E. Stability results
- Static view of tests (not executed): coverage spans AI config/privacy/resilience, invoice OCR normalization and contract type, proof flows (EXIF, AI review requirement, payment), PSP webhooks, scheduler lock, spend/transactions, and health telemetry. 【F:tests/test_ai_config.py†L1-L44】【F:tests/test_ai_privacy.py†L1-L120】【F:tests/test_invoice_ocr.py†L1-L140】【F:tests/test_psp_webhook.py†L1-L200】【F:tests/test_scheduler_lock.py†L1-L120】
- Skips/xfails: none apparent from static inspection.
- Static review notes: synchronous AI/OCR inside request path; geofence math uses float; settings cache may delay flag/secret rotation; some duplicate idempotency header checks in transactions router; logging configured globally but minimal structure.

## F. Security & integrity
- AuthN/Z: API-key dependency with scopes (sender/support/admin) and legacy dev key guarded by ENV; approvals/reads audited. 【F:app/security.py†L13-L77】【F:app/routers/apikeys.py†L96-L167】
- Input validation: Pydantic models bound lengths/patterns (ProofCreate fields, ProofDecision regex, spend/payee limits). 【F:app/schemas/proof.py†L5-L38】【F:app/routers/spend.py†L64-L116】
- File/proof validation: EXIF/geofence validation with hard 422s on geofence/age, manual review paths for softer errors; hash uniqueness at DB level. 【F:app/services/proofs.py†L126-L198】【F:app/models/proof.py†L17-L28】
- Secrets/config: Settings load from `.env`, PSP webhook secrets required at startup (non-dev) and validated per request with timestamp drift; AI/OCR flags default false. 【F:app/config.py†L35-L75】【F:.env.example†L1-L25】【F:app/main.py†L38-L78】【F:app/services/psp_webhooks.py†L100-L190】
- Logging/audit: AuditLog entries for API key use, proof submission/AI/OCR events, PSP webhook handling, user creation, transactions; health exposes secret fingerprints without raw secrets. 【F:app/security.py†L55-L76】【F:app/services/proofs.py†L358-L405】【F:app/routers/health.py†L42-L76】

## G. Observability & operations
- Logging: global configuration via `app/core/logging`/database module uses console handler INFO; FastAPI lifespan logs startup/shutdown and scheduler status. 【F:app/core/database.py†L1-L22】【F:app/main.py†L38-L134】
- Error handling: Generic and HTTP exception handlers return structured error_response; proof/PSP services raise HTTPException with codes. 【F:app/main.py†L136-L160】【F:app/services/proofs.py†L173-L197】【F:app/services/psp_webhooks.py†L120-L181】
- Alembic migrations: multiple revisions including AI/OCR fields and idempotency; current head expected via health check; no execution performed. 【F:alembic/versions/c6f0c1c0b8f4_add_invoice_fields_to_proofs.py†L1-L28】【F:alembic/versions/1b7cc2cfcc6e_add_ai_review_fields_to_proofs.py†L1-L21】
- Deployment: APScheduler optional with DB lock; settings support CORS, Prometheus, Sentry; AI/OCR provider keys read from env.

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority (P0/P1/P2) | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Monetary geofence & float use | Geofence coordinates/radius stored as Float; potential precision drift affecting validation distance. | Medium | Medium | P0 | Migrate geofence fields to Decimal/NUMERIC; adjust validation to Decimal math and update migrations. 【F:app/models/milestone.py†L32-L52】 |
| R1b | Amount validation 422 | Invoice normalization hard-fails proofs when currency/amount invalid without user guidance. | Medium | Medium | P1 | Return detailed error codes and allow retry; add UI guidance; consider soft-fail to manual review with audit flag. 【F:app/services/proofs.py†L102-L120】 |
| R2 | PSP webhook lifecycle | Startup check only; settings cache TTL may allow stale secrets; replay window fixed at 300s. | High | Low | P0 | Reduce settings cache TTL or reload per request; document secret rotation; shorten replay TTL or persist events with expiry. 【F:app/config.py†L96-L116】【F:app/services/psp_webhooks.py†L40-L76】 |
| R3 | Audit trail gaps | No dedicated audit for escrow state transitions aside from proof/payments; scheduler actions not audited. | Medium | Medium | P1 | Add AuditLog entries on escrow status changes and scheduler job runs; expose audit export endpoint. |
| R4 | FastAPI lifespan reliance | Uses lifespan context; if misconfigured, scheduler lock may not release; no health endpoint for uvicorn workers. | Medium | Low | P1 | Add shutdown exception handling and heartbeat failure alerts; document single-runner requirement. 【F:app/main.py†L64-L134】 |
| R5 | AI default safety | AI circuit breaker is per-process; missing OpenAI key returns fallback but increments error counter; potential sensitive metadata leakage if new keys added without AI_ALLOWED list. | Medium | Medium | P0 | Persist AI circuit breaker metrics; expand allowlist tests; ensure mask_metadata_for_ai drops unknown keys with explicit audit; expose AI toggle in config UI. 【F:app/services/ai_proof_advisor.py†L196-L247】【F:app/utils/masking.py†L114-L180】 |
| R6 | OCR robustness | OCR stub called with empty bytes and dummy provider; enabling real provider could block request thread. | Medium | Low | P2 | Add async/off-thread OCR pipeline and size limits; gate by feature flag with timeout handling. 【F:app/services/proofs.py†L87-L99】【F:app/services/invoice_ocr.py†L179-L217】 |
| R7 | Settings TTL | 60s cache may delay PSP/AI/OCR flag/secret rotation. | Medium | Medium | P1 | Allow configurable TTL or per-request fresh settings for security-sensitive paths (webhooks/AI). 【F:app/config.py†L96-L116】 |
| R8 | Idempotency duplication | transactions.post_transaction checks idempotency header twice; could hide missing logic for other endpoints. | Low | Medium | P2 | Refactor to shared dependency; extend idempotency to decision endpoints. 【F:app/routers/transactions.py†L46-L68】 |

## I. AI Proof Advisor, OCR & risk scoring (dedicated section)
### I.1 AI architecture
- Flags: AI_PROOF_ADVISOR_ENABLED/PROVIDER/MODEL/TIMEOUT default to disabled with OpenAI key optional; Invoice OCR flags default to disabled/dummy provider. 【F:app/config.py†L54-L68】【F:.env.example†L10-L25】
- Modules: ai_proof_flags (runtime flag helpers), ai_proof_advisor (OpenAI client with masking/circuit breaker/fallback), document_checks (backend comparisons), invoice_ocr (dummy OCR, normalization, enrichment). 【F:app/services/ai_proof_flags.py†L5-L22】【F:app/services/ai_proof_advisor.py†L196-L247】【F:app/services/document_checks.py†L5-L82】【F:app/services/invoice_ocr.py†L179-L305】

### I.2 AI integration into proof flows
- PHOTO proofs: after EXIF/geofence validation, AI advisory called only when ai_enabled; sanitized context masks mandate/backend/document metadata; failures logged and do not block auto-approval; AI results stored in metadata and dedicated columns with audit log. 【F:app/services/proofs.py†L126-L244】【F:app/services/ai_proof_advisor.py†L196-L247】【F:app/utils/masking.py†L66-L132】【F:app/services/proofs.py†L329-L396】
- NON-PHOTO proofs: OCR-enriched metadata, backend document checks computed, AI advisory optional and non-blocking, stored similarly; manual review remains default (no auto-approve). 【F:app/services/proofs.py†L83-L290】
- Storage: ai_risk_level/ai_score/ai_flags/ai_explanation/ai_checked_at/ai_reviewed_by/ai_reviewed_at persisted; clients cannot set these via ProofCreate. 【F:app/models/proof.py†L22-L47】【F:app/schemas/proof.py†L5-L38】

### I.3 OCR & backend_checks
- Invoice OCR: feature-flagged; dummy provider returns disabled payload; normalization validates amount/currency; enrichment avoids overwriting existing metadata and logs result. 【F:app/services/invoice_ocr.py†L179-L305】
- Document backend checks: compare expected amount/currency/IBAN/date/supplier from proof_requirements versus metadata; tolerant to missing values and return structured check dict used in AI context. 【F:app/services/document_checks.py†L17-L82】
- Integration: backend_checks passed into AI context for non-photo proofs; OCR outputs included in metadata sent to AI after masking. 【F:app/services/proofs.py†L245-L285】【F:app/utils/masking.py†L114-L180】

### I.4 AI/OCR-specific risks
| ID | Domain (AI/OCR) | Risk | Impact | Likelihood | Priority | Recommended fix |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | AI availability | In-memory circuit breaker resets per worker; repeated failures across replicas not aggregated. | Medium | Medium | P1 | Persist counters in DB/metrics; expose health alert when circuit opens. |
| A2 | Privacy | mask_metadata_for_ai drops unknown keys without audit; potential leakage if new fields bypass allowlist. | High | Medium | P0 | Add audit of redacted keys; enforce allowlist in schemas; unit tests for new metadata fields. 【F:app/utils/masking.py†L114-L180】 |
| A3 | Client tampering | AI fields exposed in read but not write; DB still accepts direct writes if API bypassed. | Medium | Low | P1 | Add DB triggers or server-side checks on update endpoints (none currently) and restrict update routes. 【F:app/schemas/proof.py†L11-L31】 |
| A4 | OCR blocking | OCR called synchronously with empty bytes; enabling real provider could slow or fail requests. | Medium | Medium | P1 | Move OCR to background task with stored status; add timeout and max file size guard. 【F:app/services/invoice_ocr.py†L179-L217】 |
| A5 | AI prompt drift | System prompt hardcoded; no versioning or checksum stored with AI results. | Medium | Medium | P2 | Store prompt version in AI audit payload and proof metadata for traceability. 【F:app/services/ai_proof_advisor.py†L74-L143】 |

## J. Roadmap to a staging-ready MVP
- P0 checklist:
  - Migrate geofence floats to Decimal/NUMERIC; validate distances deterministically. 【F:app/models/milestone.py†L32-L52】
  - Shorten settings cache or bypass for PSP webhook/AI/OCR paths to avoid stale secrets/flags. 【F:app/config.py†L96-L116】
  - Strengthen AI privacy allowlist with audits/tests; persist circuit breaker metrics. 【F:app/utils/masking.py†L114-L180】【F:app/services/ai_proof_advisor.py†L196-L247】
  - Document and monitor OCR/AI timeout behavior to avoid request blocking. 【F:app/services/invoice_ocr.py†L179-L217】
- P1 checklist:
  - Add audits for escrow status transitions and scheduler job execution. 【F:app/models/audit.py†L8-L17】【F:app/main.py†L64-L134】
  - Improve proof normalization UX (detailed error codes, retry guidance) and consider soft-fail to manual review. 【F:app/services/proofs.py†L102-L120】
  - Persist AI prompt/version and expose AI/OCR metrics in health. 【F:app/services/ai_proof_advisor.py†L196-L247】【F:app/services/invoice_ocr.py†L118-L123】
- P2 checklist:
  - Introduce structured logging with correlation IDs; expand Prometheus metrics. 【F:app/core/database.py†L1-L22】【F:app/routers/health.py†L20-L109】
  - Add pagination/filtering to user/alert listings; extend idempotency helpers to all monetary endpoints. 【F:app/routers/users.py†L1-L55】【F:app/routers/transactions.py†L46-L68】
  - Add async OCR provider integration with configurable providers.
- **Verdict: NO-GO for staging with 10 real users until P0 items are addressed**, especially monetary precision, settings refresh for webhook secrets, and AI privacy hardening.

## K. Verification evidence
- Alembic: `alembic current`, `alembic heads`, `alembic history --verbose` would validate that AI/OCR migrations (invoice fields, AI review fields, ai_score numeric) are applied; health endpoint checks expected head vs alembic_version. 【F:alembic/versions/c6f0c1c0b8f4_add_invoice_fields_to_proofs.py†L1-L28】【F:alembic/versions/1b7cc2cfcc6e_add_ai_review_fields_to_proofs.py†L1-L21】【F:app/routers/health.py†L52-L84】
- Tests: `pytest -q` would cover AI flags/privacy, invoice OCR, proof flows, PSP webhook signature/replay, scheduler lock, spend/transaction idempotency, and health telemetry per files listed above; not executed here (static analysis only). 【F:tests/test_ai_config.py†L1-L44】【F:tests/test_invoice_ocr.py†L1-L140】【F:tests/test_psp_webhook.py†L1-L200】【F:tests/test_scheduler_lock.py†L1-L120】
- Key references: proof validation/AI integration, masking rules, config defaults, and router inventories cited throughout sections above.
