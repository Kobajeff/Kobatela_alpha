# Kobatela_alpha — Capability & Stability Audit (2025-11-19)

## A. Executive summary
- **Runtime configuration refresh plus `/health` telemetry exposes PSP rotation state, AI/OCR toggles, and scheduler liveness without redeploying.**【F:app/config.py†L32-L128】【F:app/routers/health.py†L1-L34】
- **Proof ingestion chains hard validations (EXIF/geofence), Decimal-safe OCR enrichment, backend checks, and AI advisory writes to dedicated columns so reviewers see both metadata and AI conclusions.**【F:app/services/proofs.py†L51-L220】【F:app/services/invoice_ocr.py†L17-L134】【F:app/services/document_checks.py†L1-L169】【F:app/models/proof.py†L10-L37】
- **PSP webhooks enforce dual-secret HMACs, timestamp drift, and idempotent event storage before settlement handlers mutate payments.**【F:app/routers/psp.py†L19-L60】【F:app/services/psp_webhooks.py†L23-L188】
- **Escrow, milestone, payment, and spend flows rely on Numeric(18,2) amounts plus header-enforced idempotency keys to block double spends.**【F:app/models/escrow.py†L23-L55】【F:app/models/milestone.py†L32-L60】【F:app/models/payment.py†L21-L40】【F:app/routers/spend.py†L75-L178】
- **Audit/masking utilities sanitize sensitive data before persistence or API responses, and `/users/{id}` now records `AuditLog` entries for forensic traceability.**【F:app/utils/audit.py†L12-L107】【F:app/utils/masking.py†L1-L110】【F:app/routers/users.py†L17-L80】

Major risks / limitations:
- **Proof invoice totals live only in schemaless JSON, so upstream floats can still drift after OCR normalization (P0 monetary safety).**【F:app/models/proof.py†L24-L37】【F:app/services/proofs.py†L67-L135】
- **Several modules (e.g., `app/main.py`) cache `settings = get_settings()` at import, bypassing the TTL refresh that PSP and AI governance rely on (P0 PSP lifecycle).**【F:app/main.py†L21-L138】【F:app/config.py†L91-L128】
- **High-sensitivity read endpoints like `/escrows/{id}` and `/payments/execute/{id}` still lack explicit audit logging even though user and transaction routes do (P0 business audit).**【F:app/routers/escrow.py†L19-L93】【F:app/routers/payments.py†L18-L22】
- **Scheduler locks expire after 10 minutes but carry no owner metadata or heartbeat, so mandate cleanup can silently stall for an entire TTL window (P0 lifecycle).**【F:app/models/scheduler_lock.py†L10-L17】【F:app/services/scheduler_lock.py†L30-L75】
- **Masking is allowlist-based; new OCR metadata keys pass through to AI prompts or API clients until code changes (P0 AI/OCR governance).**【F:app/utils/masking.py†L1-L110】【F:app/services/invoice_ocr.py†L118-L134】

Readiness score: **75 / 100** — Core fintech and AI/OCR flows work end-to-end with rich tests, but the remaining P0 governance gaps must be closed before inviting external pilot customers.

## B. Capability map (current features)
### B.1 Functional coverage
| Feature | Endpoints / modules involved | Status (OK / Partial / Missing) | Notes |
| --- | --- | --- | --- |
| Health & runtime introspection | `/health`, runtime state helpers | Partial | Surface PSP, AI, OCR, and scheduler flags but omit DB connectivity and Alembic drift checks.【F:app/routers/health.py†L1-L34】【F:app/core/runtime_state.py†L1-L13】 |
| User & API key lifecycle | `/users`, `/apikeys` | Partial | Create/read flows exist with audit logging, but no pagination or search for larger tenant ops.【F:app/routers/users.py†L17-L80】【F:app/routers/apikeys.py†L63-L175】 |
| Escrow lifecycle | `/escrows/*` | OK | Creation, deposits, delivery decisions, and reads enforce sender scopes plus idempotency headers.【F:app/routers/escrow.py†L19-L93】 |
| Mandates & usage spend | `/mandates`, `/spend/*`, `/transactions` | OK | Mandates feed usage controls; spend and transaction routes require scoped API keys and `Idempotency-Key` headers.【F:app/routers/mandates.py†L13-L32】【F:app/routers/spend.py†L34-L178】【F:app/routers/transactions.py†L25-L121】 |
| Proof submission & AI advisory | `/proofs`, proof services | OK | Photo proofs enforce EXIF/geofence before optional AI; documents trigger OCR, backend checks, and AI storage of risk metadata.【F:app/routers/proofs.py†L24-L54】【F:app/services/proofs.py†L51-L220】 |
| Payments & PSP integration | `/payments/execute/{id}`, `/psp/webhook` | Partial | Manual payment execution plus webhook settlement exist, but there are no read/list endpoints and PSP TTL cache can lag rotations.【F:app/routers/payments.py†L18-L22】【F:app/routers/psp.py†L19-L60】【F:app/main.py†L21-L138】 |
| Alerts & monitoring | `/alerts` | OK | Admin/support users can list alerts with optional type filters.【F:app/routers/alerts.py†L1-L25】 |
| AI & OCR toggles | `ai_proof_flags`, `invoice_ocr` | Partial | Helpers pull live settings per call, yet metadata masking is best-effort and no telemetry counters exist.【F:app/services/ai_proof_flags.py†L1-L31】【F:app/services/invoice_ocr.py†L17-L134】 |

### B.2 End-to-end journeys supported today
- **Photo proof & payout:** `/proofs` submission validates EXIF/geofence, calls AI if enabled, and can auto-approve milestones leading to payment execution.【F:app/routers/proofs.py†L24-L54】【F:app/services/proofs.py†L79-L205】
- **Invoice proof with OCR:** Document uploads enrich metadata via OCR, compute backend comparisons, and pass sanitized context to AI reviewers.【F:app/services/invoice_ocr.py†L102-L134】【F:app/services/document_checks.py†L36-L169】【F:app/services/ai_proof_advisor.py†L237-L357】
- **Usage spend with policy enforcement:** `/spend` endpoints create categories, merchants, allowlists, and idempotent purchases backed by spend idempotency tests.【F:app/routers/spend.py†L34-L178】【F:tests/test_spend_idempotency.py†L1-L88】
- **PSP settlement lifecycle:** `/psp/webhook` verifies rotating secrets and timestamps, persists events, then settles or errors payments with audit masking.【F:app/routers/psp.py†L19-L60】【F:app/services/psp_webhooks.py†L58-L187】
- **Admin onboarding:** `/apikeys` and `/users` work together to issue scoped credentials while logging creation/reads for compliance.【F:app/routers/apikeys.py†L63-L175】【F:app/routers/users.py†L17-L80】

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request model | Response model | HTTP codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/health` | `health.healthcheck` | None | – | – | dict | 200【F:app/routers/health.py†L1-L34】 |
| POST | `/users` | `users.create_user` | API key | admin/support | `UserCreate` | `UserRead` | 201, 400【F:app/routers/users.py†L17-L53】 |
| GET | `/users/{user_id}` | `users.get_user` | API key | admin/support | – | `UserRead` | 200, 404【F:app/routers/users.py†L55-L80】 |
| POST | `/apikeys` | `apikeys.create_api_key` | API key | admin | `CreateKeyIn` | `ApiKeyCreateOut` | 201, 400【F:app/routers/apikeys.py†L63-L115】 |
| GET | `/apikeys/{api_key_id}` | `apikeys.get_apikey` | API key | admin | – | `ApiKeyRead` | 200, 404【F:app/routers/apikeys.py†L117-L130】 |
| DELETE | `/apikeys/{api_key_id}` | `apikeys.revoke_apikey` | API key | admin | – | – | 204, 404【F:app/routers/apikeys.py†L132-L175】 |
| POST | `/mandates` | `mandates.create_mandate` | API key | sender | `UsageMandateCreate` | `UsageMandateRead` | 201【F:app/routers/mandates.py†L13-L25】 |
| POST | `/mandates/cleanup` | `mandates.cleanup_expired_mandates` | API key | sender | – | `{expired}` | 202【F:app/routers/mandates.py†L27-L32】 |
| POST | `/escrows` | `escrow.create_escrow` | API key | sender | `EscrowCreate` | `EscrowRead` | 201【F:app/routers/escrow.py†L19-L27】 |
| POST | `/escrows/{id}/deposit` | `escrow.deposit` | API key + header | sender | `EscrowDepositCreate` + `Idempotency-Key` | `EscrowRead` | 200【F:app/routers/escrow.py†L29-L41】 |
| POST | `/escrows/{id}/mark-delivered` | `escrow.mark_delivered` | API key | sender | `EscrowActionPayload` | `EscrowRead` | 200【F:app/routers/escrow.py†L43-L52】 |
| POST | `/escrows/{id}/client-approve` | `escrow.client_approve` | API key | sender | optional payload | `EscrowRead` | 200【F:app/routers/escrow.py†L54-L63】 |
| POST | `/escrows/{id}/client-reject` | `escrow.client_reject` | API key | sender | optional payload | `EscrowRead` | 200【F:app/routers/escrow.py†L65-L74】 |
| POST | `/escrows/{id}/check-deadline` | `escrow.check_deadline` | API key | sender | – | `EscrowRead` | 200【F:app/routers/escrow.py†L76-L84】 |
| GET | `/escrows/{id}` | `escrow.read_escrow` | API key | sender/support/admin | – | `EscrowRead` | 200, 404【F:app/routers/escrow.py†L86-L93】 |
| POST | `/proofs` | `proofs.submit_proof` | API key | sender | `ProofCreate` | `ProofRead` | 201, 404, 409, 422【F:app/routers/proofs.py†L24-L35】 |
| POST | `/proofs/{id}/decision` | `proofs.decide_proof` | API key | support/admin | `ProofDecision` | `ProofRead` | 200, 400, 404【F:app/routers/proofs.py†L37-L54】 |
| POST | `/spend/categories` | `spend.create_category` | API key | admin/support | `SpendCategoryCreate` | `SpendCategoryRead` | 201【F:app/routers/spend.py†L34-L46】 |
| POST | `/spend/merchants` | `spend.create_merchant` | API key | admin/support | `MerchantCreate` | `MerchantRead` | 201【F:app/routers/spend.py†L48-L60】 |
| POST | `/spend/allow` | `spend.allow_usage` | API key | admin/support | `AllowedUsageCreate` | dict | 201【F:app/routers/spend.py†L62-L73】 |
| POST | `/spend/purchases` | `spend.create_purchase` | API key + header | sender/admin | `PurchaseCreate` + `Idempotency-Key` | `PurchaseRead` | 201, 400【F:app/routers/spend.py†L75-L98】 |
| POST | `/spend/allowed` | `spend.add_allowed_payee` | API key | admin/support | `AddPayeeIn` | dict | 201【F:app/routers/spend.py†L100-L134】 |
| POST | `/spend` | `spend.spend` | API key + header | sender/admin | `SpendIn` + `Idempotency-Key` | dict | 200, 400【F:app/routers/spend.py†L137-L178】 |
| POST | `/payments/execute/{id}` | `payments.execute_payment` | API key | sender | – | `PaymentRead` | 200【F:app/routers/payments.py†L18-L22】 |
| POST | `/psp/webhook` | `psp.psp_webhook` | none (PSP secret) | PSP | raw JSON | `{ok}` | 200, 401, 503【F:app/routers/psp.py†L19-L60】 |
| GET | `/alerts` | `alerts.list_alerts` | API key | admin/support | query `type` | list[`AlertRead`] | 200【F:app/routers/alerts.py†L1-L25】 |
| POST | `/allowlist` | `transactions.add_to_allowlist` | API key | admin | `AllowlistCreate` | dict | 201【F:app/routers/transactions.py†L25-L38】 |
| POST | `/certified` | `transactions.add_certification` | API key | admin | `CertificationCreate` | dict | 201【F:app/routers/transactions.py†L40-L53】 |
| POST | `/transactions` | `transactions.post_transaction` | API key + header | admin | `TransactionCreate` + `Idempotency-Key` | `TransactionRead` | 201, 400【F:app/routers/transactions.py†L55-L89】 |
| GET | `/transactions/{id}` | `transactions.get_transaction` | API key | admin | – | `TransactionRead` | 200, 404【F:app/routers/transactions.py†L93-L121】 |

## D. Data model & state machines
- **Entities:**
  - *EscrowAgreement* — Numeric(18,2) `amount_total`, deadline, JSON release config, statuses tracked via enum and indexes for status/deadline queries.【F:app/models/escrow.py†L12-L43】
  - *EscrowDeposit* — Amount, FK to escrow, unique/idempotent `idempotency_key` per deposit.【F:app/models/escrow.py†L45-L55】
  - *Milestone* — Per-escrow sequences with Numeric amount, proof type, optional geofence floats, JSON `proof_requirements`, and status enum for WAITING→PAID transitions.【F:app/models/milestone.py†L21-L62】
  - *Proof* — Unique SHA256 per upload, JSON metadata, AI advisory columns (risk level, score, flags, explanation, timestamps) plus status string (PENDING/APPROVED/REJECTED).【F:app/models/proof.py†L10-L37】
  - *Payment* — Numeric amount, optional milestone FK, unique PSP reference/idempotency key, PaymentStatus enum for PENDING→SETTLED/ERROR.【F:app/models/payment.py†L21-L40】
  - *SchedulerLock* — Single-row lock table storing lock name and acquisition timestamp for TTL eviction.【F:app/models/scheduler_lock.py†L10-L17】
  - *AuditLog/APIKey/User/Transaction/Alert* — Provide governance, credentialing, and compliance (see respective models referenced by routers above).
- **State machines:**
  - *Escrow lifecycle* — Agreements begin DRAFT, move to FUNDED after deposit, reach RELEASABLE upon proof acceptance, then RELEASED/REFUNDED/CANCELLED based on client actions processed in `app/services/escrow`. Status enum plus events table track transitions.【F:app/models/escrow.py†L12-L43】【F:app/routers/escrow.py†L43-L84】
  - *Milestones* — WAITING→PENDING_REVIEW upon proof submission, APPROVED/REJECTED via `proofs.decide_proof`, and PAYING/PAID as payments finalize (driven by payment services).【F:app/models/milestone.py†L21-L60】【F:app/services/proofs.py†L51-L220】
  - *Payments* — PENDING→SENT via manual `/payments/execute`, SETTLED/ERROR via PSP webhook service referencing PaymentStatus enum and settlement helpers.【F:app/models/payment.py†L21-L40】【F:app/routers/payments.py†L18-L22】【F:app/services/psp_webhooks.py†L102-L187】
  - *Proofs* — Submitted proofs store metadata and AI fields; statuses are updated during reviewer decisions with audit requirements for AI-flagged approvals.【F:app/services/proofs.py†L275-L399】

## E. Stability results
- **Test execution (`pytest -q`):** 82 tests passed with two warnings (Pydantic class-based `config` deprecation and SQLAlchemy transaction rollback notice).【828f2c†L1-L14】 Coverage spans AI config/privacy, proofs, escrow, payments, spend idempotency, PSP webhooks, scheduler lock, health telemetry, invoice OCR, and document backend checks (see `tests/` listing).【ee395a†L1-L10】【F:tests/test_ai_config.py†L1-L24】【F:tests/test_ai_privacy.py†L1-L80】【F:tests/test_invoice_ocr.py†L1-L63】【F:tests/test_document_checks.py†L1-L27】
- **Migrations:** `alembic upgrade head` succeeds on SQLite, replaying AI-proof and scheduler-lock migrations sequentially.【c3c70f†L1-L3】【9e58e8†L1-L13】
- **Warnings explained:**
  - *PydanticDeprecatedSince20* — emitted by upstream dependency; requires migrating schemas to ConfigDict eventually.【828f2c†L3-L9】
  - *SQLAlchemy transaction already deassociated* — occurs inside `tests/conftest.py` rollback cleanup when asserting idempotency failure; benign but worth hardening fixture logic.【828f2c†L9-L13】
- **Static review notes:**
  - Module-level globals in `app/main.py` and other modules still capture stale settings, undermining TTL refresh benefits for PSP/AI toggles.【F:app/main.py†L21-L138】
  - Proof metadata remains JSON; migrating to typed columns would prevent Decimal drift despite OCR normalization.【F:app/models/proof.py†L24-L37】
  - Scheduler locking lacks owner metadata or heartbeat, so long-running tasks may hold the lock silently until TTL expiry.【F:app/services/scheduler_lock.py†L30-L75】
  - `/escrows/{id}` and payment execution endpoints do not log audits despite handling PII; instrumentation is inconsistent across routers.【F:app/routers/escrow.py†L86-L93】【F:app/routers/payments.py†L18-L22】

## F. Security & integrity
- **AuthN/Z:** API key dependencies extract `Authorization`/`X-API-Key`, validate hashed prefixes, log use, and enforce scopes per endpoint; legacy dev key is gated by environment toggles.【F:app/security.py†L20-L155】
- **Input validation:** Pydantic schemas enforce numeric bounds and regex decisions for proofs, spend payloads, and transactions (see `ProofCreate`, `ProofDecision`, `SpendIn`, etc.).【F:app/schemas/proof.py†L7-L44】【F:app/routers/spend.py†L137-L178】
- **File/proof validation:** `submit_proof` enforces EXIF/geofence/age constraints before storing, throws 422 on hard failures, and only calls AI after deterministic checks; non-photo proofs always require manual review despite AI hints.【F:app/services/proofs.py†L79-L220】
- **Secrets & config:** `.env.example` documents PSP, AI, and OCR keys disabled by default; settings TTL cache fetches values every 60 seconds, but module-level singletons bypass it.【F:.env.example†L1-L25】【F:app/config.py†L91-L128】
- **Audit/logging:** Utility masks PII before writing `AuditLog`, API key usage and `/users` reads log events, PSP failures log masked secret digests, and proofs mask metadata before returning to clients.【F:app/utils/audit.py†L12-L107】【F:app/routers/users.py†L55-L80】【F:app/services/psp_webhooks.py†L37-L99】【F:app/routers/proofs.py†L16-L35】

## G. Observability & operations
- **Logging:** Lifespan startup configures logging, enforces PSP secret presence, and records scheduler lock acquisition; Prometheus and Sentry hooks are optional per settings.【F:app/main.py†L26-L138】
- **HTTP error handling:** Global exception handlers wrap unexpected errors with structured JSON; PSP routes emit reasoned HTTP statuses for signature failures.【F:app/main.py†L123-L138】【F:app/routers/psp.py†L35-L60】
- **Migrations health:** Alembic history covers AI-proof fields, milestone proof requirements, and scheduler locks; operators can verify via `alembic current`, `heads`, and `history --verbose` (upgrade already executed in this audit).【9e58e8†L1-L13】【F:alembic/versions/013024e16da9_add_ai_fields_to_proofs.py†L1-L47】【F:alembic/versions/9c697d41f421_add_proof_requirements_to_milestones.py†L1-L27】【F:alembic/versions/a9bba28305c0_add_scheduler_locks_table.py†L1-L29】
- **Deployment specifics:** Lifespan gating ensures DB init and scheduler locking before serving. `/health` surfaces toggles but lacks DB ping or Alembic hash; scheduler telemetry depends on in-process flag only.【F:app/main.py†L26-L138】【F:app/routers/health.py†L19-L34】【F:app/core/runtime_state.py†L1-L13】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority (P0/P1/P2) | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Proof monetary fields | Invoice totals/currencies exist only in JSON metadata; mismatched scale can leak or block payouts despite Decimal OCR normalization. | High-value payouts miscomputed or stuck | Medium | P0 | Add typed Numeric columns on `proofs` for `invoice_total_amount`/`currency`, backfill via migration, and hydrate during `submit_proof` to guarantee Decimal math (~0.5 day).【F:app/models/proof.py†L24-L37】【F:app/services/proofs.py†L67-L135】 |
| R2 | PSP webhook governance | Modules still hold `settings = get_settings()` at import (e.g., `app/main.py`), so TTL refresh never triggers and secret rotations may be ignored until restart. | Spoofed webhooks during rotation | High | P0 | Replace module-level globals with runtime `get_settings()` calls or dependency injection; add `/health` digest fingerprints so ops can verify active secrets (~1 day).【F:app/main.py†L21-L138】 |
| R3 | Business lifecycle audit | Escrow/payment read endpoints do not log `AuditLog` entries even though `/users` and transactions do; PII reads leave no trace. | Limited forensic evidence | Medium | P0 | Instrument remaining read endpoints with `actor_from_api_key` + `log_audit`, including escrow, payment, spend, and proof reads (~0.5 day).【F:app/routers/escrow.py†L86-L93】【F:app/routers/payments.py†L18-L22】 |
| R4 | Scheduler lifecycle | Lock table only stores `name`/`acquired_at`, so a stuck worker can hold the lock for 10 minutes without identification or heartbeat. | Mandate cleanup pauses silently | Medium | P0 | Extend lock model with `owner_id` + `expires_at`, refresh heartbeat periodically, and expose lock metadata on `/health` (~1 day).【F:app/models/scheduler_lock.py†L10-L17】【F:app/services/scheduler_lock.py†L30-L75】 |
| R5 | AI/OCR privacy | Masking allowlist does not cover new OCR fields, so sensitive metadata may leak into AI prompts or responses until code updates. | Regulatory/privacy breach | Medium | P0 | Introduce schema-driven allowlists per proof type, default-mask unknown keys, and add regression tests for new OCR outputs (~1 day).【F:app/utils/masking.py†L1-L110】【F:app/services/invoice_ocr.py†L118-L134】 |
| R6 | Health telemetry | `/health` omits DB/alembic checks and scheduler owner info, so ops may miss drift or lock contention; tests already assert certain payload keys. | Late detection of infra issues | Medium | P1 | Add DB ping, Alembic head hash, scheduler lock age, and AI/OCR error counters to `/health` plus tests (~0.5 day).【F:app/routers/health.py†L19-L34】【F:tests/test_health.py†L1-L40】 |
| R7 | PSP settlement audit | `_mark_payment_settled` lacks `AuditLog` writes; only failures are logged, reducing reconciliation fidelity. | PSP dispute investigation harder | Low | P2 | Record masked audit entries on settlement success, including PSP reference and payment ID (~0.25 day).【F:app/services/psp_webhooks.py†L121-L187】 |

## I. AI Proof Advisor, OCR & risk scoring (dedicated section)
### I.1 AI architecture
- Settings disable AI/OCR by default, document provider/model/timeout, and expose OpenAI keys via `.env` with optional values; TTL caching refreshes every 60 seconds.【F:app/config.py†L32-L128】【F:.env.example†L10-L25】
- `ai_proof_flags` wraps `get_settings()` for every check so toggles respond to runtime changes without redeploying.【F:app/services/ai_proof_flags.py†L1-L31】
- AI modules include prompt building and sanitization (`mask_proof_metadata`) plus AI/OCR/document services enumerated in the capability map.【F:app/services/ai_proof_advisor.py†L237-L357】【F:app/services/invoice_ocr.py†L17-L134】【F:app/services/document_checks.py†L1-L169】

### I.2 AI integration into proof flows
- Photo proofs: run EXIF/geofence validators first, auto-approve only when rules succeed, and wrap AI calls in try/except that log failures and fall back to manual review; AI results stored in metadata plus proof columns (`ai_risk_level`, etc.).【F:app/services/proofs.py†L79-L205】【F:app/models/proof.py†L28-L37】
- Document proofs: always manual review but may run OCR/back-end checks before AI; AI context includes sanitized metadata, backend comparisons, and mandate info, and fallbacks never block the proof. Clients cannot set AI fields because `ProofCreate` lacks them while `ProofRead` exposes them read-only.【F:app/services/proofs.py†L194-L220】【F:app/schemas/proof.py†L7-L36】
- AI advisor short-circuits when disabled or missing API key/SDK, emits warnings, and returns fallback flags for reviewer awareness.【F:app/services/ai_proof_advisor.py†L237-L357】

### I.3 OCR & backend_checks
- Invoice OCR uses provider stubs, normalizes totals via Decimal quantization, uppercases currencies, keeps raw totals, masks IBAN to last4, and writes `ocr_status`/`ocr_provider` without overwriting client metadata. Exceptions mark status `error` but do not raise.【F:app/services/invoice_ocr.py†L39-L134】
- `compute_document_backend_checks` converts all numbers to Decimal, compares currencies/amounts, checks IBAN last4, date ranges, and supplier names, returning structured dicts even when data is missing; these results flow into AI context.【F:app/services/document_checks.py†L1-L169】【F:app/services/proofs.py†L194-L220】
- Tests assert OCR disabled/success flows, non-overwrite guarantees, Decimal comparisons, and difference detection.【F:tests/test_invoice_ocr.py†L1-L63】【F:tests/test_document_checks.py†L1-L27】

### I.4 AI/OCR-specific risks
| ID | Domain (AI/OCR) | Risk | Impact | Likelihood | Priority | Recommended fix |
| --- | --- | --- | --- | --- | --- | --- |
| AI-1 | AI governance | Masking allowlist misses unforeseen OCR keys, risking leakage to AI providers or API consumers. | Privacy breach | Medium | P0 | Default-deny unknown keys and enforce per-proof-type schemas before sending data to AI.【F:app/utils/masking.py†L1-L110】 |
| AI-2 | AI observability | No metrics/counters for AI fallbacks; ops cannot detect provider outages quickly. | Silent AI failures | Medium | P1 | Emit Prometheus counters (`ai_proof_calls_total`, `ai_proof_fallback_total`) and log structured reasons for dashboards.【F:app/services/ai_proof_advisor.py†L237-L357】 |
| AI-3 | OCR provenance | Metadata only indicates `ocr_status`; reviewers may miss when OCR contradicts provided totals beyond backend check dicts. | Reviewer confusion | Low | P2 | Surface backend check mismatches explicitly in proof responses and require manual acknowledgment on approval.【F:app/services/document_checks.py†L36-L169】【F:app/services/proofs.py†L194-L220】 |
| AI-4 | Settings cache bypass | Modules caching `settings` bypass TTL, meaning AI toggles may remain stuck until restart. | AI misconfiguration persists | Medium | P0 | Refactor to dependency-injected settings or call `get_settings()` inside request handlers/services (~0.5 day).【F:app/main.py†L21-L138】 |

**Tests to add:**
1. `/health` should reflect AI/OCR toggles when `get_settings()` values change mid-process (monkeypatch `ai_proof_flags` and `invoice_ocr`).
2. `mask_proof_metadata` should mask newly introduced OCR fields (e.g., `supplier_tax_id`) before AI context serialization.
3. `call_ai_proof_advisor` should surface fallback flags/metadata when JSON decoding fails.
4. Proof submission should persist backend check mismatches to metadata/AI fields for reviewer consumption.

## J. Roadmap to a staging-ready MVP
- **P0 checklist (blocking):**
  1. Add typed invoice total/currency columns plus migration and hydration logic to eliminate JSON-only monetary comparisons (R1).【F:app/models/proof.py†L24-L37】
  2. Remove module-level `settings` globals (main app, DB helpers, etc.) so TTL refresh governs PSP secrets and AI toggles (R2/R5).【F:app/main.py†L21-L138】
  3. Extend audit logging to escrow, payment, spend, and proof reads for complete lifecycle tracking (R3).【F:app/routers/escrow.py†L86-L93】【F:app/routers/payments.py†L18-L22】
  4. Enhance scheduler lock with owner identifiers/heartbeat exposure and surface age on `/health` (R4).【F:app/services/scheduler_lock.py†L30-L75】【F:app/routers/health.py†L19-L34】
  5. Default-mask unknown OCR metadata keys and add regression tests for AI fallbacks to satisfy AI/OCR governance (R5).【F:app/utils/masking.py†L1-L110】【F:app/services/invoice_ocr.py†L118-L134】
- **P1 checklist:**
  1. Add `/health` DB ping/Alembic hash plus Prometheus counters for AI/OCR fallbacks (R6, AI-2).【F:app/routers/health.py†L19-L34】【F:app/services/ai_proof_advisor.py†L237-L357】
  2. Introduce payment/PSP read/list endpoints with pagination and audit logs for reconciliation.
  3. Harden scheduler metrics (lock owner, TTL) and add tests for stale-lock eviction.
- **P2 checklist:**
  1. Implement OCR provider integration (Mindee/Tabscanner) and expand metadata mapping/test coverage.
  2. Build admin UI filters for alerts/users/api keys with pagination.
  3. Add AI prompt templates per proof type and experimentation flags for future LLM providers.

**Verdict: NO-GO for a staging with 10 real users** until P0 checklist items (typed invoice fields, live settings refresh, full audit logging, scheduler telemetry, AI/OCR masking) are closed; once resolved, the remaining gaps are operational rather than architectural.

## K. Verification evidence
- **Migrations:** `alembic upgrade head` executed successfully in this audit, replaying all historical versions through scheduler-lock creation, confirming schema parity with models.【c3c70f†L1-L3】【9e58e8†L1-L13】 Operators should still run `alembic current`, `alembic heads`, and `alembic history --verbose` pre-release to detect drift.
- **Tests:** `pytest -q` completed with 82 passing tests and the two known warnings described earlier; this suite covers AI flags/privacy, OCR/document checks, PSP webhooks, escrow lifecycle, scheduler locking, and health telemetry.【828f2c†L1-L14】【ee395a†L1-L10】
- **File references:** This report cites concrete modules (e.g., proofs, OCR, AI advisor, masking, routers, models) so reviewers can cross-check claims directly within the repository using the referenced paths and line numbers.
