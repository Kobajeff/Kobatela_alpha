# Kobatela_alpha — Capability & Stability Audit (2025-11-19)

## A. Executive summary
- Core fintech surfaces (escrow, mandates, spend, proofs, PSP webhook) are implemented with scoped API-key auth and idempotency keys, giving a solid baseline for double-spend protection.
- Proof ingestion chains hard validations (EXIF/geofence) with optional AI/OCR enrichment, storing AI outputs in read-only columns while leaving client input immutable.
- Runtime config is centralized via `Settings` with per-call reads for PSP/AI/OCR values, and `/health` exposes scheduler lock status plus PSP secret fingerprints for rotation visibility.
- Alembic history is present and models use `Numeric` for monetary values; migrations cover AI fields, scheduler lock owner/expiry, and JSON metadata fields needed for proofs and mandates.
- Tests span spend idempotency, proofs, PSP webhook secrets, scheduler locking, transactions audit, and health telemetry, indicating deliberate coverage across money, governance, and runtime safety.

Major risks / limitations:
- Monetary/OCR precision risk: invoice totals live in JSON metadata and can originate from floats; no schema-level constraints enforce scale/precision across OCR-enriched fields (P0 R1).
- PSP webhook protection hinges on shared secret only; there is no HMAC/timestamp verification to block replay or tampering (P0 R2).
- Audit trail gaps: escrow reads/payments lack `AuditLog` coverage; AI/OCR actions are not audited for operator oversight (P0 R3/R5).
- Lifecycle resilience: scheduler lock heartbeat is present, but app still uses mixed startup patterns and lacks DB connectivity checks in `/health` (P0 R4).
- AI/OCR governance: prompts can receive unsanitized metadata keys; AI advisor errors could bubble up without clear fallback telemetry or rate limits (P0 R5).

Readiness score: **68 / 100** — Functional breadth is good, but PSP hardening, audit coverage, monetary precision, and AI/OCR governance need P0 remediation before exposing to external users.

## B. Capability map (current features)
### B.1 Functional coverage
| Feature | Endpoints / modules involved | Status (OK / Partial / Missing) | Notes |
| --- | --- | --- | --- |
| Health & runtime introspection | `/health`, runtime state helpers | Partial | Returns PSP fingerprints, AI/OCR toggles, scheduler status; does not probe DB/migrations. |
| User & API key lifecycle | `/users`, `/apikeys` | Partial | CRUD for users and API keys with scoped access and audit on reads; lacks pagination/search. |
| Escrow lifecycle | `/escrows/*` | OK | Create, deposit (idempotent), deliver, approve/reject, deadline check, read. |
| Mandates & usage spend | `/mandates`, `/spend/*`, `/transactions` | OK | Mandate create/cleanup, spend categories/merchants/allowlist, purchases with idempotency, transactions CRUD. |
| Proof submission & AI advisory | `/proofs`, proof services | OK | Photo proofs validate EXIF/geofence; documents run OCR + backend checks + optional AI; decisions available. |
| Payments & PSP integration | `/payments/execute/{id}`, `/psp/webhook` | Partial | Manual execution plus webhook handling; webhook uses shared secret only and minimal replay protection. |
| Alerts & monitoring | `/alerts` | OK | List alerts with optional type filter. |
| AI & OCR toggles | `ai_proof_flags`, `invoice_ocr` | Partial | Runtime flags honored; masking best-effort and no usage metrics. |

### B.2 End-to-end journeys supported today
- Photo proof & payout: proof submission → validation → optional AI → milestone decision → payment execution.
- Invoice proof with OCR: document upload → OCR enrichment → backend checks → AI context construction → reviewer decision.
- Usage spend with policy enforcement: mandate setup → categories/merchants → allowlists → purchases with idempotency and transaction records.
- PSP settlement lifecycle: webhook verification → event persistence → settlement/error handling tied to payments.
- Admin onboarding: user + API key issuance with scoped permissions and audit of sensitive reads.

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
| POST | `/psp/webhook` | `psp.psp_webhook` | secret header | PSP | raw JSON | `{ok}` | 200, 401, 503 |
| GET | `/alerts` | `alerts.list_alerts` | API key | admin/support | query `type` | list[`AlertRead`] | 200 |
| POST | `/allowlist` | `transactions.add_to_allowlist` | API key | admin | `AllowlistCreate` | dict | 201 |
| POST | `/certified` | `transactions.add_certification` | API key | admin | `CertificationCreate` | dict | 201 |
| POST | `/transactions` | `transactions.post_transaction` | API key + Idempotency-Key | admin | `TransactionCreate` | `TransactionRead` | 201, 400 |
| GET | `/transactions/{id}` | `transactions.get_transaction` | API key | admin | – | `TransactionRead` | 200, 404 |

## D. Data model & state machines
- Entities:
  - EscrowAgreement: `amount_total Numeric(18,2)`, deadline, JSON release config, status enum; FK to sender/beneficiary.
  - EscrowDeposit: `amount Numeric(18,2)`, FK to escrow, unique `idempotency_key` for deposits.
  - Milestone: sequence per escrow, `amount Numeric(18,2)`, proof type, optional geofence float coords, JSON `proof_requirements`, status enum.
  - Proof: unique `sha256`, JSON `metadata`, AI columns (`ai_risk_level`, `ai_score`, `ai_flags`, `ai_explanation`, `ai_checked_at`), status string.
  - Payment: `amount Numeric(18,2)`, optional milestone FK, unique PSP reference + idempotency key, status enum with settlement/error fields.
  - SchedulerLock: `name` unique, `owner`, `acquired_at`, `expires_at`, created/updated timestamps.
  - APIKey/User: API key scope enum with hashed key storage; users have role enum and email uniqueness.
  - Spend domain: categories, merchants, allowed usages, purchases, mandates, transactions with Numeric amounts and idempotency keys.
- State machines:
  - Escrow: CREATED → (deposited) → DELIVERED → APPROVED/REJECTED; deadline check can auto-reject or progress.
  - Milestone: WAITING → (proof submitted) → PENDING_REVIEW → APPROVED/REJECTED → PAID after payment execution.
  - Proof: SUBMITTED → PENDING_REVIEW → APPROVED/REJECTED; AI fields populate on submission when enabled.
  - Payment: PENDINGSETTLED/ERROR reflecting PSP execution and webhook settlement.
  - Scheduler lock: owned per runner with TTL, refreshed via heartbeat, releasable on shutdown.

## E. Stability results
- Static view of tests (not executed; inferred from test files):
  - Coverage includes spend idempotency, proofs submission/decisions, PSP webhook secrets and runtime refresh, health endpoint fields, scheduler lock contention/expiry, transactions audit logging, alerts, API keys, and OCR/AI flag behavior.
  - No skipped/xfail markers observed in reviewed tests.
- Static review notes:
  - Broad try/except usage around AI/OCR integrations is limited; some external calls may still raise and surface 500s.
  - DB session handling largely uses dependency-injected sessions with commits inside services; beware mixed SessionLocal usage in scheduler lock service.
  - Geofence calculations use float lat/lon; precision adequate for checks but watch for missing normalization.
  - Proof metadata remains schemaless JSON; downstream analytics require validation layer to prevent float drift.

## F. Security & integrity
- AuthN/Z: API key header with scope enforcement; PSP webhook relies on shared secret(s) rather than user auth.
- Input validation: Pydantic schemas with enums for proof types/statuses; monetary fields use Decimal via `Numeric(18,2)`; geofence floats are optional.
- File/proof validation: content-type checks, EXIF/GPS extraction, geofence radius check, sha256 uniqueness; decisions gated by roles.
- Secret management: Settings from environment; PSP secrets rotated via primary/next; AI/OCR keys optional and read at runtime; no caching at import.
- Audit/logging: `AuditLog` model records actions for API keys/users and transactions; PSP webhook events stored before processing; missing audits on some sensitive reads/writes (escrow/payment/AI usage).

## G. Observability & operations
- Logging: standard logging setup; services log key actions (webhook verification, AI/OCR outcomes) without structured IDs.
- Error handling: FastAPI HTTPException with error_response helper; some unhandled exceptions could bubble from external calls.
- Alembic migrations: sequential version files include proof AI fields, invoice/OCR, scheduler lock owner/expiry; `alembic.ini` configured for env-based DB URL.
- Deployment: scheduler uses AsyncIOScheduler with heartbeat; `/health` exposes scheduler and PSP fingerprints but not DB connectivity.

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority (P0/P1/P2) | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Monetary/OCR metadata | OCR-enriched amounts/currency stored in JSON allow float drift and lack precision guarantees | High | Medium | P0 | Add typed columns or validators for OCR fields; coerce to Decimal; extend migrations to enforce Numeric(18,2). |
| R2 | PSP webhook | Shared-secret only; no HMAC/timestamp, replay protection, or strict secret requirement | High | Medium | P0 | Enforce HMAC signature + timestamp window; reject when secrets missing; add tests and docs. |
| R3 | Audit coverage | Escrow/payment reads & AI/OCR decisions lack AuditLog entries | Medium | Medium | P0 | Instrument audit logging for sensitive reads/writes; ensure DB transaction safety. |
| R4 | Lifecycle/startup | Mixed startup patterns; `/health` lacks DB check; scheduler heartbeat depends on SessionLocal in service layer | Medium | Medium | P0 | Consolidate lifespan usage, add DB connectivity check to health, and ensure heartbeat session handling is safe. |
| R5 | AI/OCR governance | AI prompts may include unsanitized metadata; AI/OCR errors may propagate; AI enabled via env without rate limits | Medium | Medium | P0 | Add metadata allowlist/filtering, wrap AI/OCR calls with catch/log fallback, add rate limiting/timeout configuration. |
| R6 | Privacy | Metadata may include sensitive fields sent to AI/OCR beyond IBAN last4; masking is best-effort | High | Medium | P1 | Enforce field-level redaction before AI/OCR calls; document data handling; add tests. |
| R7 | Observability | No metrics/tracing; limited health info | Medium | Medium | P1 | Add structured logging/metrics, expose DB/alembic status in health. |
| R8 | Validation | Geofence and document checks rely on floats/strings without strict bounds | Medium | Low | P2 | Tighten Pydantic validators (range for lat/lon, date parsing). |

## I. AI Proof Advisor, OCR & risk scoring (dedicated section)
### I.1 AI architecture
- Config via `Settings`: `AI_PROOF_ADVISOR_ENABLED` (bool, default False), provider/model/timeout keys, `OPENAI_API_KEY`; `.env.example` lists AI and OCR env vars disabled by default.
- Modules: `app/services/ai_proof_flags.py` (runtime flag helpers), `app/services/ai_proof_advisor.py` (OpenAI/GPT integration and context building), `app/services/document_checks.py` (backend comparisons), `app/services/invoice_ocr.py` (OCR toggles and enrichment), AI fields on `app/models/proof.py` with exposure in read schemas only.

### I.2 AI integration into proof flows
- In `submit_proof`, AI is invoked after validations: for photos, EXIF/geofence and sha256 uniqueness precede AI; for documents, OCR enrichment and backend checks build context.
- AI is optional: guarded by `ai_enabled()`; results stored in metadata and AI columns (`ai_risk_level`, `ai_score`, `ai_flags`, `ai_explanation`, `ai_checked_at`) set server-side, not client-controlled.
- AI output does not auto-approve payments; decisions remain manual via support/admin roles.

### I.3 OCR & backend_checks
- `invoice_ocr` checks `INVOICE_OCR_ENABLED/PROVIDER/API_KEY`; `_call_external_ocr_provider` returns empty payload when provider is `none`, avoiding failures.
- `_normalize_invoice_ocr` maps provider fields to standard metadata (amount, currency, date, number, supplier, iban_last4/masked, location).
- `enrich_metadata_with_invoice_ocr` merges OCR data without overwriting existing non-empty fields; errors are logged and ignored.
- `compute_document_backend_checks` compares OCR/metadata against `proof_requirements` (amount, currency, IBAN last4, date, supplier), returning structured booleans/None used in AI context.

### I.4 AI/OCR-specific risks
| ID | Domain (AI/OCR) | Risk | Impact | Likelihood | Priority | Recommended fix |
| --- | --- | --- | --- | --- | --- | --- |
| AI1 | AI prompt hygiene | Unsanitized metadata keys/values may leak sensitive data to OpenAI | High | Medium | P0 | Implement allowlist/field-level filtering before building AI context; mask personal data. |
| AI2 | AI failure handling | Exceptions from OpenAI/OCR may bubble up, causing 5xx on proof submission | Medium | Medium | P0 | Wrap external calls in try/except with timeouts; log and continue with advisory absent. |
| AI3 | AI config guarding | AI could be enabled in prod without explicit opt-in controls or rate limits | Medium | Medium | P0 | Require explicit flag + API key presence; add per-request timeout/rate limiting and monitoring counters. |
| AI4 | OCR precision | Float amounts from OCR not coerced to Decimal; downstream comparisons may drift | High | Medium | P0 | Normalize to Decimal with quantization; add schema fields for OCR outputs. |
| AI5 | Auditability | AI/OCR invocations not logged in AuditLog | Medium | Medium | P1 | Add audit entries or structured logs for AI/OCR calls with non-sensitive metadata. |

## J. Roadmap to a staging-ready MVP
- P0 checklist (must fix before pilot):
  - Add HMAC + timestamp verification to `/psp/webhook`; reject missing/invalid secrets; document rotation.
  - Enforce Decimal precision for OCR-derived monetary fields; migrate critical OCR outputs to typed columns.
  - Instrument AuditLog for escrow/payment reads and AI/OCR decisions; ensure transactional writes.
  - Harden AI/OCR calls with try/except, timeouts, and metadata allowlisting; add rate limits.
  - Consolidate app startup to lifespan, validate DB connectivity in `/health`, and ensure scheduler heartbeat uses safe session scope.
- P1 checklist (before broader rollout):
  - Add structured logging/metrics (per endpoint + AI/OCR usage), DB/alembic health checks, and PSP replay detection tests.
  - Enhance pagination/search for users/alerts; add proof/transaction listing endpoints with filters.
  - Expand masking/redaction for metadata and AI prompts; add privacy notice in docs.
- P2 checklist (scalability/comfort):
  - Introduce circuit breakers for external AI/OCR/PSP calls, caching for AI-safe prompts, and background retries for transient failures.
  - Add role-based dashboards or telemetry endpoints; implement configuration hot-reload metrics.
- **Verdict: NO-GO for staging with 10 real users** until P0 items above are closed; after mitigation, reassess with focused penetration and load testing.

## K. Verification evidence
- Migrations: `alembic/versions` contains sequential revisions including scheduler lock owner/expiry and AI/OCR-related schema; `alembic.ini` references env-based DB URL. Running `alembic current/heads/history` would confirm head alignment (not executed here; static inference only).
- Tests: `tests/` includes suites for spend idempotency, proofs (including AI/OCR toggles), PSP webhook secrets, health fingerprints, scheduler lock contention/expiry, and transaction audit logging. `pytest -q` would exercise these domains (not executed; static inference only).
- Key file anchors for claims: routers under `app/routers/*` define endpoints; models under `app/models/*` show Numeric monetary fields and AI columns; services `app/services/ai_proof_advisor.py`, `document_checks.py`, `invoice_ocr.py` implement AI/OCR logic; scheduler lock logic in `app/services/scheduler_lock.py` with owner/expiry; settings in `app/config.py` hold AI/OCR/PSP flags.
