# Kobatela_alpha — Capability & Stability Audit (2025-11-18)

## A. Executive summary
- Hardened API-key–based access control plus role-aware dependencies on every write endpoint, with centralized masking in `app/utils/audit.py` so sensitive actors and payloads are recorded deterministically across services (`users`, `escrows`, `proofs`, `spend`, `payments`).
- Proof ingestion layers deterministic EXIF/geofence validation, optional invoice OCR enrichment, structured document backend checks, and the AI Proof Advisor with masked contexts before calling OpenAI, then persists ai_* verdicts for downstream governance (`app/services/proofs.py`, `ai_proof_advisor.py`, `document_checks.py`, `invoice_ocr.py`).
- Monetary operations consistently rely on SQLAlchemy `Numeric(18,2)` columns plus `_to_decimal` normalization and explicit idempotency lookups for escrows, purchases, payments, and transactions, preventing rounding drift and double-execution across `app/services/*.py`.
- PSP webhook processing couples HMAC + timestamp drift validation, dual-secret rotation fields, and idempotent event storage before touching payments, closing the loop with `finalize_payment_settlement` and `AuditLog` trails (`app/routers/psp.py`, `app/services/psp_webhooks.py`).
- Operational envelope includes FastAPI `lifespan` startup with mandatory PSP secret guardrails, JSON logging, Prometheus/Sentry toggles, Alembic-led schema management, and a scheduler hook for mandate expiry.

Major risks / limitations:
- `/escrows/{id}` lacks `require_scope`, so any bearer can enumerate escrow states and monetary totals without audit traces, violating confidentiality and undermining lifecycle controls (`app/routers/escrow.py`).
- Escrow deposits accept (but do not enforce) `Idempotency-Key`, so retries or duplicate PSP callbacks can mint extra deposits and inflate balances (R1 monetary safety gap in `app/routers/escrow.deposit` + `app/services/escrow.deposit`).
- PSP webhook rotation is manual; secrets are loaded once at startup and there is no health signal if both `psp_webhook_secret` and `_next` are unset or stale while APScheduler keeps running (R2 in `app/main.py`, `app/services/psp_webhooks.py`).
- Business lifecycle audit loses coverage on read-only but sensitive calls (escrow fetch, proof metadata reads) because no `AuditLog` is written nor is authentication enforced (R3 across `app/routers/escrow.py`, `app/routers/proofs.py`).
- AI/OCR guardrails rely on best-effort masking, yet `metadata` echoes back whatever the AI/OCR pipelines added; without per-field whitelists, invoice data (supplier city, totals) may still exit the platform via GET /proofs responses (R5 privacy risk).

Readiness score: **78 / 100** — functional MVP is strong, but P0 monetary/idempotency, PSP rotation, audit coverage, and AI/OCR privacy issues must be fixed before exposing 10 external users.

## B. Capability map (current features)
### B.1 Functional coverage
| Feature | Endpoints / modules involved | Status (OK / Partial / Missing) | Notes |
| --- | --- | --- | --- |
| Health & monitoring | GET `/health` (`app/routers/health.py`), JSON logging, optional Prometheus/Sentry in `app/main.py` | OK | Stateless ping plus structured logging; no DB check yet. |
| User & API key management | `/users`, `/apikeys` routers + `app/security.py` | OK | Admin/support scopes create users, generate/revoke keys, each mutation logged via `AuditLog`. |
| Escrow lifecycle | `/escrows` router + `app/services/escrow.py`, `payments.py`, `milestones.py` | OK | Create, deposit, mark delivered, approve/reject, deadline auto-approve, auto payouts with EscrowEvents. GET lacks auth. |
| Usage mandates & spend | `/mandates`, `/spend`, `app/services/mandates.py`, `spend.py`, `usage.py` | OK | Create mandates (sender scope), allow merchants/categories, enforce Decimal, Idempotency-Key required for purchases and spend. |
| Transactions / allowlist | `/allowlist`, `/certified`, `/transactions` + `app/services/transactions.py` | OK | Admin-only allowlist/certify flows with alerts on violations and idempotent transaction creation. |
| Proof submission & decisions | `/proofs`, `app/services/proofs.py`, `rules.py`, `document_checks.py` | OK | Photo proofs auto-validated/paid, documents enriched via OCR/backend checks, AI advisory gated by flag. |
| PSP webhook & payouts | `/psp/webhook`, `app/services/psp_webhooks.py`, `payments.py` | OK | HMAC + timestamp verification, dual secret rotation, idempotent event store, settlement/resolution pipelines. |
| AI Proof Advisor | `ai_proof_flags.py`, `ai_proof_advisor.py` | Partial | Flag defaults to False, sanitized context + fallback; no streaming/per-proof toggles. |
| Invoice OCR | `invoice_ocr.py`, `submit_proof` hook | Partial | Feature-flagged stub returns `{}`; metadata enrichment only when enabled. |

### B.2 End-to-end journeys supported today
- **Simple escrow funding & release**: `/users` → `/escrows` (create) → `/escrows/{id}/deposit` with Idempotency-Key → `/escrows/{id}/mark-delivered` → `/proofs` (photo) → auto-approve + `payments.execute_payout` → `/psp/webhook` confirms settlement.
- **Multi-milestone mandate with AI advisory**: `/mandates` (sender scope) defines usage window → `/proofs` (PDF/INVOICE) triggers invoice OCR, backend checks, AI Proof Advisor context; reviewers call `/proofs/{id}/decision` with notes when AI flagged.
- **Usage spend via allowlisted payees**: `/spend/categories` + `/spend/merchants` + `/spend/allow` configure policies → `/spend/allowed` registers payees → `/spend/purchases` (Idempotency-Key) consumes mandate budgets → `/spend` triggers escrow payouts settled via `payments` and `psp_webhooks`.
- **Admin PSP monitoring**: `/apikeys` issue keys → `/psp/webhook` ingests events → `/payments/execute/{id}` retries failed payouts → `AuditLog` + `alerts` capture anomalies.
- **Document proof with backend comparisons**: Milestone proof_requirements JSON + `/proofs` submission → `document_checks` compare amount/IBAN/date/supplier → AI context includes backend signals + metadata for manual reviewers.

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request model | Response model | HTTP codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/health` | `health.healthcheck` | None | N/A | – | `dict` | 200 |
| POST | `/users` | `users.create_user` | API key | admin/support | `UserCreate` | `UserRead` | 201, 400 |
| GET | `/users/{id}` | `users.get_user` | API key | admin/support | – | `UserRead` | 200, 404 |
| POST | `/apikeys` | `apikeys.create_api_key` | API key | admin | `CreateKeyIn` | `ApiKeyCreateOut` | 201, 400 |
| GET | `/apikeys/{id}` | `apikeys.get_apikey` | API key | admin | – | `ApiKeyRead` | 200, 404 |
| DELETE | `/apikeys/{id}` | `apikeys.revoke_apikey` | API key | admin | – | `Response` | 204, 404 |
| GET | `/alerts` | `alerts.list_alerts` | API key + dependency | admin/support | query `type` | list[`AlertRead`] | 200 |
| POST | `/mandates` | `mandates.create_mandate` | API key | sender | `UsageMandateCreate` | `UsageMandateRead` | 201, 400, 404, 409 |
| POST | `/mandates/cleanup` | `mandates.cleanup_expired_mandates` | API key | sender | – | `{expired:int}` | 202 |
| POST | `/spend/categories` | `spend.create_category` | API key | admin/support | `SpendCategoryCreate` | `SpendCategoryRead` | 201, 400 |
| POST | `/spend/merchants` | `spend.create_merchant` | API key | admin/support | `MerchantCreate` | `MerchantRead` | 201, 400, 404 |
| POST | `/spend/allow` | `spend.allow_usage` | API key | admin/support | `AllowedUsageCreate` | `{status}` | 201, 400 |
| POST | `/spend/purchases` | `spend.create_purchase` | API key | sender/admin | `PurchaseCreate` + `Idempotency-Key` header | `PurchaseRead` | 201, 400, 403, 404, 409 |
| POST | `/spend/allowed` | `spend.add_allowed_payee` | API key | admin/support | inline `AddPayeeIn` | `{id,...}` | 201, 409 |
| POST | `/spend` | `spend.spend` | API key | sender/admin | inline `SpendIn` + `Idempotency-Key` | `{payment_id,...}` | 200, 400, 403, 404, 409 |
| POST | `/allowlist` | `transactions.add_to_allowlist` | API key | admin | `AllowlistCreate` | `{status}` | 201 |
| POST | `/certified` | `transactions.add_certification` | API key | admin | `CertificationCreate` | `{status}` | 201 |
| POST | `/transactions` | `transactions.post_transaction` | API key | admin | `TransactionCreate` + `Idempotency-Key` | `TransactionRead` | 201, 400 |
| GET | `/transactions/{id}` | `transactions.get_transaction` | API key | admin | – | `TransactionRead` | 200, 404 |
| POST | `/escrows` | `escrow.create_escrow` | API key | sender | `EscrowCreate` | `EscrowRead` | 201, 404 |
| POST | `/escrows/{id}/deposit` | `escrow.deposit` | API key | sender | `EscrowDepositCreate` (+ optional `Idempotency-Key`) | `EscrowRead` | 200, 400, 404 |
| POST | `/escrows/{id}/mark-delivered` | `escrow.mark_delivered` | API key | sender | `EscrowActionPayload` | `EscrowRead` | 200, 404 |
| POST | `/escrows/{id}/client-approve` | `escrow.client_approve` | API key | sender | optional `EscrowActionPayload` | `EscrowRead` | 200, 404 |
| POST | `/escrows/{id}/client-reject` | `escrow.client_reject` | API key | sender | optional `EscrowActionPayload` | `EscrowRead` | 200, 404 |
| POST | `/escrows/{id}/check-deadline` | `escrow.check_deadline` | API key | sender | – | `EscrowRead` | 200 |
| GET | `/escrows/{id}` | `escrow.read_escrow` | **None** | – | – | `EscrowRead` | 200, 404 |
| POST | `/proofs` | `proofs.submit_proof` | API key | sender | `ProofCreate` | `ProofRead` | 201, 404, 409, 422 |
| POST | `/proofs/{id}/decision` | `proofs.decide_proof` | API key | support/admin | `ProofDecision` | `ProofRead` | 200, 400, 404, 409 |
| POST | `/payments/execute/{id}` | `payments.execute_payment` | API key | sender | – | `PaymentRead` | 200, 404, 409 |
| POST | `/psp/webhook` | `psp.psp_webhook` | HMAC secret headers | PSP | JSON body | `{ok,...}` | 200, 401, 503 |

## D. Data model & state machines
- **Entities**:
  - `EscrowAgreement` (Numeric `amount_total`, `EscrowStatus` enum, deadlines, release conditions, events) with deposits and events for audit.【F:app/models/escrow.py†L12-L63】
  - `Milestone` (unique `(escrow_id, idx)`, Numeric `amount`, JSON `proof_requirements`, geofence floats, `MilestoneStatus` enum) linking to `Proof`.【F:app/models/milestone.py†L19-L63】
  - `Proof` stores metadata JSON, unique `sha256`, status (`PENDING/APPROVED/REJECTED`), and AI governance columns (`ai_risk_level`, `ai_score`, `ai_flags`, `ai_explanation`, `ai_checked_at`, reviewer fields).【F:app/models/proof.py†L10-L35】
  - `Payment` (Numeric `amount`, `PaymentStatus`, optional milestone FK, idempotency key) ensures positive amount and indexes for reconciliation.【F:app/models/payment.py†L17-L40】
  - `UsageMandate`, `AllowedPayee`, `AllowedUsage`, `Purchase`, `Transaction`, `Alert`, `AuditLog`, `ApiKey`, `PSPWebhookEvent`, and `User` enforce Numeric(18,2) monetary fields, unique constraints, and statuses for spend/micro-ledger flows.【F:app/models/usage_mandate.py†L1-L44】【F:app/models/spend.py†L1-L58】【F:app/models/transaction.py†L1-L31】
- **State machines**:
  - Escrow: `DRAFT` → `FUNDED` (after deposits) → `RELEASABLE` (proof uploaded) → `RELEASED` or `REFUNDED/CANCELLED`. Deadline checks call `client_approve`, and payments finalize with EscrowEvents/AuditLog entries.【F:app/services/escrow.py†L63-L182】
  - Milestone/Proof: `WAITING` → `PENDING_REVIEW` (proof submitted) → `APPROVED` (auto or manual) → `PAID` once payments sent. Sequence guard ensures only current milestone accepts proofs.【F:app/services/proofs.py†L58-L209】
  - Payments: `PENDING` → `SENT` → `SETTLED` (PSP webhook/manual execution) or `ERROR`. Idempotency keys and EscrowEvents persist each transition.【F:app/services/payments.py†L82-L236】
  - Usage Mandates: `ACTIVE` → `CONSUMED` or `EXPIRED` via `_consume_mandate_atomic` and scheduler cleanup; audit events recorded on each change.【F:app/services/mandates.py†L48-L126】【F:app/services/spend.py†L240-L338】

## E. Stability results
- Environment prep:
  - `python -m venv .venv` **failed** twice because ensurepip hung; captured traceback for audit.【ecdbbc†L1-L20】【b3bbd1†L1-L18】
  - Fallback `pip install -r requirements.txt` succeeded globally (see full package list).【448273†L1-L38】【2f495b†L1-L25】
- Database migrations:
  - `alembic upgrade head` applied through `1b7cc2cfcc6e` covering AI review columns.【4980af†L1-L4】【b6ad7b†L1-L11】
  - `alembic current` → `1b7cc2cfcc6e (head)`; `alembic heads` matches; `alembic history --verbose` lists eleven revisions without divergence.【cbc0b2†L1-L4】【e907c4†L1-L2】【24da15†L1-L56】
- Tests:
  - `pytest -q` → **67 passed, 1 skipped**, warnings: deprecated Pydantic config and skipped async test lacking plugin.【29997b†L1-L18】
- Static review hot spots:
  - Lack of auth on `GET /escrows/{id}` (privacy + unauthorized read of monetary state).【F:app/routers/escrow.py†L54-L69】
  - Optional `Idempotency-Key` on deposits/spend allows accidental double deposits. Enforcement only exists in spend endpoints, not escrow deposits.【F:app/routers/escrow.py†L22-L41】
  - APScheduler uses in-memory store without distributed lock; running multiple pods risks duplicate `expire_mandates_once` execution (log warning but no enforcement).【F:app/main.py†L24-L63】
  - AI/OCR failures logged but not surfaced to clients; metadata may silently omit context, so reviewers may not notice fallback mode.

## F. Security & integrity
- **AuthN/Z**: API key extraction via `Authorization: Bearer` or `X-API-Key`, hashed with `SECRET_KEY`, and scope-checked per router (`require_scope`). Legacy dev key allowed only in dev, logged via `AuditLog`.【F:app/security.py†L16-L103】
- **Input validation**: Pydantic schemas enforce Decimal > 0 for money, allowed currencies, `Idempotency-Key` required in spend/purchase routers, and regex-constrained proof decisions. Missing validations: `/escrows/{id}` GET has no auth; `EscrowDeposit` idempotency optional.
- **File/proof validation**: `rules.validate_photo_metadata` enforces EXIF timestamp, geofence, and source; `submit_proof` raises 422 on hard errors, ensures sequential milestones, autopays only when validations succeed, and wraps AI calls in try/except to avoid blocking flow.【F:app/services/rules.py†L11-L72】【F:app/services/proofs.py†L64-L208】
- **Secrets/config**: `.env` template ships PSP and AI/OCR flags defaulting to safe values (AI & OCR disabled). `app/main.lifespan` aborts startup when `psp_webhook_secret` missing, preventing unprotected webhook exposure.【F:app/config.py†L35-L78】【F:.env.example†L10-L24】【F:app/main.py†L18-L50】
- **Audit/logging**: `AuditLog` entries triggered in escrow, payments, proofs, usage, transactions, API key usage, plus `EscrowEvent` timeline for payouts. However, read-only endpoints (GET /escrows) and AI metadata fetches are not audited, leaving gaps in lifecycle traceability.

## G. Observability & operations
- **Logging**: `app/core/logging.setup_logging` configures JSON formatter on startup; `lifespan` logs env and warns when scheduler enabled without distributed lock. Key services call `logger.info`/`warning` with structured extras.
- **Error handling**: Global exception handlers wrap responses into `error_response` payloads; `psp_webhook` returns 401 on signature mismatch, 503 when secret absent.
- **Migrations**: Alembic chain contiguous; `app/main` refuses to run without PSP secret; `ALLOW_DB_CREATE_ALL` gating prevents accidental `create_all` except in dev/local/test sets.
- **Deployment**: APScheduler optional via `KOB_SCHEDULER_ENABLED`; caution log warns to run on a single replica. No liveness check for scheduler health, so stuck jobs may go unnoticed.

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Escrow deposits (monetary safety) | `/escrows/{id}/deposit` treats `Idempotency-Key` as optional, so PSP retries or user refreshes can create duplicate `EscrowDeposit` rows and overfund agreements. | High (double-funding) | Medium | P0 | Require `Header(..., alias="Idempotency-Key")` in router, reject empty keys in `app/services/escrow.deposit`, and backfill unique constraint enforcement. Effort: 0.5 day plus migration for non-null key. |
| R2 | PSP webhook secrets | Secrets loaded once; no runtime health to ensure either `psp_webhook_secret` or `_next` stays populated, risking unprocessed webhooks if env unset after deploy and offering no telemetry to ops. | High (webhooks fail with 503) | Medium | P0 | Add startup probe/metrics exposing secret presence, emit alert when both secrets None, and support reloading secrets without restart (e.g., dependency that re-reads settings per request). Effort: 0.5–1 day. |
| R3 | Escrow/Proof read access audit | GET `/escrows/{id}` has no auth dependency and no audit log; proof metadata reads also lack actor tracking. Confidential financial data can leak without trace. | High (data leak, compliance breach) | High | P0 | Add `Depends(require_scope({ApiScope.sender, ApiScope.support, ApiScope.admin}))` for GETs, log read access via `AuditLog`, and retrofit tests. Effort: 1 day. |
| R4 | Scheduler / lifecycle | APScheduler runs inside FastAPI event loop with in-memory store; nothing prevents two pods from setting `SCHEDULER_ENABLED=1`, leading to duplicate mandate expiries and racey DB writes. | Medium (double expiry, noisy audits) | Medium | P0 | Introduce distributed lock (e.g., DB advisory lock) before running `expire_mandates_once`, or externalize to cron/worker. Document env var enforcement. Effort: 1–2 days. |
| R5 | AI/OCR privacy | Although `_sanitize_context` masks obvious keys, AI/OCR outputs are injected into proof metadata and echoed to clients without per-field allowlists, so supplier city, invoice totals, or other OCR-derived data may leave the platform unintentionally. | Medium (PII leakage) | High | P0 | Extend `sanitize_payload_for_audit`-style masking to proof metadata responses, or split AI/OCR data into separate secured fields, plus unit tests ensuring sensitive keys (supplier, iban) stay masked in API responses. Effort: 1–2 days. |
| R6 | Escrow read auth | Public GET `/escrows/{id}` enables enumeration of escrow status/amount without any authentication. | High | Medium | P0 | Same mitigation as R3; treat as confidentiality blocker. |
| R7 | Async test coverage | `tests/test_scopes.py::test_legacy_key_rejected_outside_dev` skipped because pytest lacks async plugin, so regressions in auth scopes may go unnoticed. | Medium | Medium | P1 | Add `pytest-asyncio` dependency, convert test to `pytest.mark.anyio`, ensure coverage. |
| R8 | AI feature toggles | `ai_enabled()` reads cached settings; toggling env at runtime requires process restart, risking partial rollouts. | Low | Medium | P2 | Recompute flag per request or add admin endpoint to flip flag with cache clear. |

## I. AI Proof Advisor, OCR & risk scoring (dedicated section)
### I.1 AI architecture
- Config: `Settings` exposes `AI_PROOF_ADVISOR_ENABLED` (default False), provider/model, resolution/pagination limits, timeout, and `OPENAI_API_KEY`. `.env.example` mirrors these and sets safe defaults (AI off, provider `openai`, stub API key).【F:app/config.py†L35-L58】【F:.env.example†L10-L24】
- Modules: `app/services/ai_proof_flags.py` centralizes `ai_enabled`, `ai_model`, and timeout values; `ai_proof_advisor.py` builds the core prompt, sanitizes contexts, masks sensitive metadata keys before calling OpenAI, and returns normalized `risk_level/score/flags/explanation`. Missing SDK or API key triggers deterministic warning results.【F:app/services/ai_proof_flags.py†L1-L17】【F:app/services/ai_proof_advisor.py†L1-L166】
- AI Proof Advisor integrates with `submit_proof`, `document_checks`, and `invoice_ocr` to produce `ai_assessment` JSON inserted into metadata and persisted in AI columns on the Proof row.【F:app/services/proofs.py†L70-L205】

### I.2 AI integration into proof flows
- **PHOTO**: After metadata validation and geofence enforcement, AI is called only when validation succeeded (`auto_approve=True`) and the feature flag is on. Failures are logged and ignored so proofs still progress. AI context includes mandate data, backend validation summary, document metadata (with sanitized storage URL). AI result stored both in metadata (`ai_assessment`) and dedicated columns (`ai_risk_level`, `ai_flags`, etc.).【F:app/services/proofs.py†L94-L171】【F:app/models/proof.py†L24-L35】
- **DOC (PDF/INVOICE/CONTRACT)**: Always manual review; AI invoked (if enabled) after `enrich_metadata_with_invoice_ocr` and `compute_document_backend_checks`, so the model sees OCR-enriched metadata plus backend comparisons (amount diff, IBAN match, date range, supplier). Exceptions are swallowed to avoid blocking review. Behavior identical when AI disabled (no metadata injection, proof remains pending).【F:app/services/proofs.py†L172-L216】
- Governance: `decide_proof` requires a reviewer note when approving AI-flagged proofs and stamps `ai_reviewed_by/ai_reviewed_at`. Tests `test_proof_ai_review.py` cover these requirements.【F:app/services/proofs.py†L218-L278】【F:tests/test_proof_ai_review.py†L1-L63】

### I.3 OCR & backend_checks
- `invoice_ocr.invoice_ocr_enabled()` reads config; `_call_external_ocr_provider` currently stubbed, returning `{}` unless provider set. `_normalize_invoice_ocr` maps provider keys to canonical metadata (amount, currency, date, number, supplier, IBAN last4, masked IBAN). `enrich_metadata_with_invoice_ocr` merges normalized values into existing metadata without overwriting non-empty fields and logs exceptions silently.【F:app/services/invoice_ocr.py†L1-L67】
- `document_checks.compute_document_backend_checks` compares milestone `proof_requirements` vs metadata (amount/currency diffs, IBAN last4 match, date ranges, supplier exact match), returning a dictionary used in AI context. Missing fields yield `None` rather than raising, so flow continues even with sparse metadata.【F:app/services/document_checks.py†L1-L88】
- Integration: `submit_proof` calls OCR enrichment immediately for doc proofs, then computes backend checks before AI invocation, ensuring AI sees both OCR-enriched metadata and structured validation signals.【F:app/services/proofs.py†L80-L215】

### I.4 AI/OCR-specific risks
| ID | Domain | Risk | Impact | Likelihood | Priority | Recommended fix |
| --- | --- | --- | --- | --- | --- | --- |
| AI-1 | AI context privacy | `_sanitize_context` masks known keys but new metadata keys (e.g., `supplier_city`) can leak raw values to OpenAI or API consumers. | Medium | Medium | P0 | Expand `SENSITIVE_KEYS`, add schema-aware whitelist for metadata forwarded to AI and API responses. |
| AI-2 | OCR reliability | `_call_external_ocr_provider` always returns `{}` unless provider implemented, yet doc proofs rely on OCR/AI context for reviewer hints. Reviewers may over-trust empty `backend_checks`. | Medium | High | P1 | Add status flags in metadata (e.g., `ocr_status`) and surface to UI/tests so humans know OCR unavailable; integrate at least one provider in staging. |
| AI-3 | Runtime toggles | `ai_enabled()` caches settings at import; flipping env vars requires restart, risking partial rollouts. | Low | Medium | P2 | Recompute flag per request or expose admin toggle endpoint that updates settings safely. |
| OCR-1 | Metadata persistence | OCR-enriched metadata merged silently; no audit trail of what fields originated from OCR vs user. | Medium | Medium | P1 | Tag OCR-derived fields (e.g., `ocr_source`) and log `AuditLog` entries when enrichment occurs for traceability. |

## J. Roadmap to a staging-ready MVP
- **P0 checklist (blockers)**:
  1. Enforce `Idempotency-Key` on escrow deposits and log duplicate attempts (R1).
  2. Add runtime/metrics guard ensuring PSP webhook secrets present and reloadable; alert when unset (R2).
  3. Secure GET `/escrows/{id}` (and other read endpoints) with `require_scope`, log read access in `AuditLog` (R3 & R6).
  4. Introduce distributed locking or single-runner enforcement for APScheduler mandate expiry (R4).
  5. Mask or segregate AI/OCR-derived metadata before returning to clients; expand sanitization for supplier/iban fields (R5, AI-1).
- **P1 checklist (before serious pilot)**:
  - Implement at least one OCR provider integration with status indicators (AI-2/OCR-1) and add unit tests covering OCR enrichment failures.
  - Ship async testing plugin to re-enable skipped legacy scope test, plus add coverage for `/escrows` auth.
  - Add alerting for AI service failures (e.g., Prometheus counters) so ops knows when proofs fall back to manual mode.
- **P2 checklist (comfort/scalability)**:
  - Provide admin endpoint or feature toggle service to flip AI/OCR settings without restarts (AI-3).
  - Extend `/health` to include DB connectivity and migration status.
  - Add bulk export/reporting endpoints with pagination and audit logging for compliance reviews.

**Verdict: NO-GO for a staging with 10 real users until P0 items above are implemented and verified.**

## K. Verification evidence
- `python -m venv .venv` (twice) → failed with KeyboardInterrupt waiting on ensurepip; tracebacks recorded in sections E & H. 【ecdbbc†L1-L20】【b3bbd1†L1-L18】
- `pip install -r requirements.txt` → all dependencies already satisfied globally. 【448273†L1-L38】【2f495b†L1-L25】
- `alembic upgrade head` → sequential migrations applied through `1b7cc2cfcc6e`. 【4980af†L1-L4】【b6ad7b†L1-L11】
- `alembic current` / `alembic heads` / `alembic history --verbose` → single head `1b7cc2cfcc6e`; history output embedded for traceability. 【cbc0b2†L1-L4】【e907c4†L1-L2】【24da15†L1-L56】
- `pytest -q` → `67 passed, 1 skipped` with warnings recorded (Pydantic config, async test skipped). 【29997b†L1-L18】
