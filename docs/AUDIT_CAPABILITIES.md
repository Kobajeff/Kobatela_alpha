# Kobatela_alpha — Capability & Stability Audit (2025-11-18)

## A. Executive summary
- API-key enforcement with scope-aware dependencies guards every router, and sensitive escrow reads now emit `ESCROW_READ` audit records so actors are traceable end to end (`app/routers/*`, `app/services/escrow.py`).
- Monetary flows use `Numeric(18,2)` columns plus `_to_decimal` normalization and `get_existing_by_key` idempotency helpers across escrows, spend, payments, and transactions, eliminating rounding drift and double-execution (`app/models/escrow.py`, `app/services/escrow.py`, `app/services/idempotency.py`).
- Proof ingestion chains EXIF/geofence rules, invoice OCR enrichment, backend comparisons, sanitized AI contexts, and masked proof responses while persisting AI verdicts in dedicated columns for reviewer governance (`app/services/proofs.py`, `app/services/document_checks.py`, `app/services/invoice_ocr.py`, `app/services/ai_proof_advisor.py`, `app/utils/masking.py`, `app/models/proof.py`).
- PSP webhooks require HMAC + timestamp validation, dual-secret rotation fields, and idempotent event storage before payments mutate, giving resilience to replayed events (`app/routers/psp.py`, `app/services/psp_webhooks.py`).
- Operational envelope relies on FastAPI lifespan startup with mandatory PSP secret guardrails, scheduler warnings, JSON logging, optional Prometheus/Sentry hooks, and `/health` surfaces PSP/scheduler readiness for ops teams (`app/main.py`, `app/routers/health.py`).

Major risks / limitations:
- `EscrowDeposit.idempotency_key` is still nullable in the schema, so historical rows bypass uniqueness despite router/service enforcement; DB-level safety remains a P0 gap (`app/models/escrow.py`).
- PSP secrets are only validated at startup; a mid-run rotation or env drift would not raise alerts even though `/health` reports only boolean status (`app/main.py`, `app/routers/health.py`).
- Sensitive GET endpoints such as `/transactions/{id}` return financial payloads without emitting `AuditLog` entries, leaving lifecycle blind spots (`app/routers/transactions.py`).
- APScheduler continues to run in-process with only documentation warning operators to keep a single runner, so a second pod could double-execute mandate expiry/payout jobs (`app/main.py`).
- AI/OCR feature toggles rely on cached `settings`, so runtime flag flips require process restarts and risk inconsistent behavior during staged rollouts (`app/services/ai_proof_flags.py`, `app/config.py`).

Readiness score: **82 / 100** — strong controls overall, but DB-level deposit idempotency, PSP secret observability, missing read audits, scheduler guardrails, and AI toggle governance must be closed before inviting 10 external staging users.

## B. Capability map (current features)
### B.1 Functional coverage
| Feature | Endpoints / modules involved | Status (OK / Partial / Missing) | Notes |
| --- | --- | --- | --- |
| Health & telemetry | `/health` + lifespan logging (`app/routers/health.py`, `app/main.py`) | OK | PSP secret + scheduler readiness reported; lacks DB connectivity check.
| User & API key lifecycle | `/users`, `/apikeys` (`app/routers/users.py`, `app/routers/apikeys.py`) | OK | Role-scoped, audited creation/revocation.
| Escrow lifecycle | `/escrows/*`, escrow service (`app/routers/escrow.py`, `app/services/escrow.py`) | OK | Create/deposit/mark delivered/client approve+reject/check deadline with audits.
| Mandates & spend controls | `/mandates`, `/spend/*`, usage services (`app/routers/mandates.py`, `app/routers/spend.py`) | OK | Covers category/merchant allowlists plus sender spend with Idempotency-Key.
| Proof submission & review with AI/OCR | `/proofs`, AI/OCR/doc-check services | OK | Metadata sanitized, AI optional, reviewer decisions persisted.
| Payments & PSP webhooks | `/payments/execute/{id}`, `/psp/webhook`, settlement services | OK | Manual execution plus signed webhook settlement with idempotent events.
| Alerts & monitoring | `/alerts` (`app/routers/alerts.py`) | OK | Admin/support visibility into backend alerts.
| AI Proof Advisor | `ai_proof_flags`, `ai_proof_advisor` | Partial | Feature off by default but settings cached; only OpenAI provider supported.
| Invoice OCR | `invoice_ocr.py` | Partial | Feature-flagged stub returns `{}` with no provider telemetry.

### B.2 End-to-end journeys supported today
- **Escrow funding through release**: `/users` → `/escrows` → `/escrows/{id}/deposit` (mandatory `Idempotency-Key`) → `/escrows/{id}/mark-delivered` → `/proofs` (photo auto-approval + AI context) → `/payments/execute/{id}` or PSP webhook settlement.
- **Usage mandate spend controls**: `/mandates` create allowances → `/spend/categories|merchants|allow|allowed` configure scope → `/spend/purchases` or `/spend` execute spending with strict idempotency and audit trails.
- **Document proof with OCR + AI advisory**: `/proofs` submission for PDF/INVOICE triggers OCR enrichment, backend checks, sanitized AI call, stored AI verdict, and manual reviewer decision.
- **PSP settlement monitoring**: `/psp/webhook` verifies signature/timestamp, stores idempotent events, updates payments, and `/health` exposes PSP secret readiness for ops.

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request model | Response model | HTTP codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/health` | `health.healthcheck` | None | – | – | dict | 200 |
| POST | `/users` | `users.create_user` | API key | admin/support | `UserCreate` | `UserRead` | 201, 400 |
| GET | `/users/{id}` | `users.get_user` | API key | admin/support | – | `UserRead` | 200, 404 |
| POST | `/apikeys` | `apikeys.create_api_key` | API key | admin | `CreateKeyIn` | `ApiKeyCreateOut` | 201, 400 |
| GET | `/apikeys/{id}` | `apikeys.get_apikey` | API key | admin | – | `ApiKeyRead` | 200, 404 |
| DELETE | `/apikeys/{id}` | `apikeys.revoke_apikey` | API key | admin | – | – | 204, 404 |
| POST | `/mandates` | `mandates.create_mandate` | API key | sender | `UsageMandateCreate` | `UsageMandateRead` | 201, 400 |
| POST | `/mandates/cleanup` | `mandates.cleanup_expired_mandates` | API key | sender | – | `{expired}` | 202 |
| POST | `/escrows` | `escrow.create_escrow` | API key | sender | `EscrowCreate` | `EscrowRead` | 201, 404 |
| POST | `/escrows/{id}/deposit` | `escrow.deposit` | API key + Idempotency-Key | sender | `EscrowDepositCreate` | `EscrowRead` | 200, 400, 404 |
| POST | `/escrows/{id}/mark-delivered` | `escrow.mark_delivered` | API key | sender | `EscrowActionPayload` | `EscrowRead` | 200, 404 |
| POST | `/escrows/{id}/client-approve` | `escrow.client_approve` | API key | sender | optional `EscrowActionPayload` | `EscrowRead` | 200, 404 |
| POST | `/escrows/{id}/client-reject` | `escrow.client_reject` | API key | sender | optional `EscrowActionPayload` | `EscrowRead` | 200, 404 |
| POST | `/escrows/{id}/check-deadline` | `escrow.check_deadline` | API key | sender | – | `EscrowRead` | 200, 404 |
| GET | `/escrows/{id}` | `escrow.read_escrow` | API key | sender/support/admin | – | `EscrowRead` | 200, 404 |
| POST | `/proofs` | `proofs.submit_proof` | API key | sender | `ProofCreate` | `ProofRead` (masked) | 201, 404, 409, 422 |
| POST | `/proofs/{id}/decision` | `proofs.decide_proof` | API key | support/admin | `ProofDecision` | `ProofRead` | 200, 400, 404, 409 |
| POST | `/spend/categories` | `spend.create_category` | API key | admin/support | `SpendCategoryCreate` | `SpendCategoryRead` | 201, 400 |
| POST | `/spend/merchants` | `spend.create_merchant` | API key | admin/support | `MerchantCreate` | `MerchantRead` | 201 |
| POST | `/spend/allow` | `spend.allow_usage` | API key | admin/support | `AllowedUsageCreate` | dict | 201 |
| POST | `/spend/allowed` | `spend.add_allowed_payee` | API key | admin/support | `AddPayeeIn` | dict | 201 |
| POST | `/spend/purchases` | `spend.create_purchase` | API key + Idempotency-Key | sender/admin | `PurchaseCreate` | `PurchaseRead` | 201, 400, 403, 404, 409 |
| POST | `/spend` | `spend.spend` | API key + Idempotency-Key | sender/admin | `SpendIn` | dict | 200, 400, 403, 404, 409 |
| POST | `/allowlist` | `transactions.add_to_allowlist` | API key | admin | `AllowlistCreate` | dict | 201 |
| POST | `/certified` | `transactions.add_certification` | API key | admin | `CertificationCreate` | dict | 201 |
| POST | `/transactions` | `transactions.post_transaction` | API key + Idempotency-Key | admin | `TransactionCreate` | `TransactionRead` | 201, 400 |
| GET | `/transactions/{id}` | `transactions.get_transaction` | API key | admin | – | `TransactionRead` | 200, 404 |
| POST | `/payments/execute/{id}` | `payments.execute_payment` | API key | sender | – | `PaymentRead` | 200, 404, 409 |
| GET | `/alerts` | `alerts.list_alerts` | API key | admin/support | query `type` | list[`AlertRead`] | 200 |
| POST | `/psp/webhook` | `psp.psp_webhook` | HMAC headers | PSP | raw JSON | `{ok}` | 200, 401, 503 |

## D. Data model & state machines
- **Entities overview**
  - `EscrowAgreement` (client/provider IDs, `Numeric(18,2)` totals, release conditions JSON, deadline, `EscrowStatus`, FK relationships to deposits/events) ensures non-negative totals and indexed deadlines (`app/models/escrow.py`).
  - `EscrowDeposit` holds Decimal amounts and unique-but-nullable `idempotency_key`, with positive amount check constraints (`app/models/escrow.py`).
  - `Milestone` (not shown above) tracks idx, Decimal amount, proof type, validators, optional geofence floats, proof requirements JSON, and statuses.
  - `Proof` stores metadata JSON, unique SHA256, statuses, and AI governance columns (`ai_risk_level`, `ai_score`, `ai_flags`, `ai_explanation`, `ai_checked_at`, reviewer fields) (`app/models/proof.py`).
  - `Payment` persists Decimal amounts, statuses, idempotency keys, PSP references, and ties to mandates/milestones (see `app/models/payment.py`).
  - `AuditLog`, `ApiKey`, `Alert`, `UsageMandate`, `AllowedPayee`, and `PSPWebhookEvent` provide lifecycle, access control, and webhook history.

- **State machines**
  - **Escrow**: `DRAFT` → `FUNDED` once deposits reach amount; `mark_delivered` sets `RELEASABLE`; `client_approve` → `RELEASED`; `client_reject` toggles `REFUNDED`/`CANCELLED`; `check_deadline` auto-approves overdue funded escrows, each transition audited and evented (`app/services/escrow.py`).
  - **Proof**: Photo proofs enforce EXIF/geofence rules and may auto-approve (plus AI advisory); document proofs remain manual but capture AI/back-end signals; decisions log reviewer + AI metadata (`app/services/proofs.py`).
  - **Payments**: Created idempotently, executed manually, settled via PSP webhook; status transitions recorded and audited (`app/services/payments.py`, `app/services/psp_webhooks.py`).

## E. Stability results
- `pytest -q`: **74 passed, 1 skipped, 2 warnings** (`tests/test_scopes.py` async skip + Pydantic config deprecation) in 4.75s (`d9314a`).
- No runtime failures observed; the async skip indicates `pytest-asyncio` is still pending, so legacy scope rejection coverage remains partial.
- Static review highlights: nullable escrow deposit idempotency keys (monetary risk), missing read audits for transactions/payments, cached AI flags blocking runtime toggle, and APScheduler double-run risk.

## F. Security & integrity
- **AuthN/Z**: Every router depends on `require_scope` or `require_api_key`, and escrow reads require sender/support/admin scopes with audit logging (`app/routers/escrow.py`, `app/services/escrow.py`).
- **Input validation**: Pydantic schemas enforce types/lengths/enums, while routers explicitly require `Idempotency-Key` headers on monetary endpoints to prevent duplicate writes (`app/routers/spend.py`, `app/routers/transactions.py`).
- **File/proof validation**: Photo proofs must pass EXIF timestamp/geofence checks; doc proofs run backend amount/date/IBAN/supplier comparisons before AI advisory, ensuring AI never replaces hard validations (`app/services/proofs.py`, `app/services/document_checks.py`).
- **Secrets & config**: Settings default AI/OCR flags to False, strip empty PSP secrets, and lifespan aborts startup when secrets missing (`app/config.py`, `app/main.py`).
- **Audit/logging**: `_audit` helper and proof submission logs persist actor/action/entity metadata for escrow state changes, deposits, AI-assisted decisions, and PSP settlement; however, transaction reads still lack audits (`app/services/escrow.py`, `app/services/proofs.py`, `app/routers/transactions.py`).

## G. Observability & operations
- JSON logging configured at startup plus Prometheus/Sentry optional hooks provide baseline telemetry; scheduler warnings highlight single-runner requirements (`app/main.py`).
- Exception handlers wrap `HTTPException` and generic exceptions into normalized JSON payloads, logging server errors centrally (`app/main.py`).
- Alembic migration chain is linear through head `1b7cc2cfcc6e`, and upgrade/current/heads/history commands run cleanly (see Section K).
- Deployment notes warn APScheduler must only run on one instance; no distributed lock exists yet, so multi-runner deployments need extra coordination (`app/main.py`).

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Escrow deposits | `EscrowDeposit.idempotency_key` nullable allows NULL rows to bypass uniqueness, so service regressions could double-credit deposits. | High monetary loss | Medium | P0 | Backfill NULL keys (hash escrow+amount+timestamp) and make column `nullable=False` via Alembic; re-run escrow tests. Effort ≈ 0.5 day.
| R2 | PSP webhook secrets | Secrets only checked at startup; mid-run rotation/env drift silently breaks signature verification. | High (missed settlements) | Medium | P0 | Add periodic secret reload or admin endpoint plus metric/alert on `/health`; surface `psp_secrets_configured` to Prometheus. Effort ≈ 0.5 day.
| R3 | Business lifecycle audit | Sensitive GETs (`/transactions/{id}`, payments, mandates) return data without `AuditLog`, hindering investigations. | High compliance risk | Medium | P0 | Mirror `get_escrow` approach: require actor + log `*_READ` audit entries for each sensitive fetch. Effort ≈ 0.5 day.
| R4 | FastAPI lifecycle / scheduler | APScheduler uses in-memory store with doc-only single-runner guidance; two pods would double-execute jobs. | Medium payout risk | Medium | P0 | Implement leader election (DB advisory lock) or runtime guard that disables scheduler when lock unavailable; add health flag. Effort ≈ 1 day.
| R5 | AI & OCR toggles | `ai_enabled()` reads cached settings; flag flips need restarts and risk inconsistent AI usage during deploys. | Medium AI-governance risk | Medium | P0 | Recompute settings per request (call `get_settings()`), add TTL caching or admin toggle endpoint, and log flag changes. Effort ≈ 0.5 day.
| R6 | OCR transparency | Provider stub returns `{}` with no `ocr_status`, so reviewers cannot tell if OCR ran, undermining trust. | Medium review quality | Medium | P1 | Store `ocr_status` and provider info in metadata + metrics; integrate at least one staging provider. Effort ≈ 0.5 day.
| R7 | Async tests | `pytest` skips async scope test, so auth regressions might slip through. | Medium testing gap | Low | P1 | Add `pytest-asyncio` dev dependency and mark coroutine tests accordingly. Effort ≈ 0.25 day.

## I. AI Proof Advisor, OCR & risk scoring (dedicated section)
### I.1 AI architecture
- Settings expose AI flags (default False), provider/model/timeout, and OpenAI key; `.env.example` mirrors these variables so AI remains opt-in (`app/config.py`).
- `ai_proof_flags.py` centralizes `ai_enabled`, provider, model, timeout; however, it reads module-level `settings`, so toggles require restarts.
- `ai_proof_advisor.py` builds structured prompts, masks metadata, calls OpenAI via `responses.create`, and returns normalized fallback results when API key/SDK missing or exceptions occur.
- `mask_proof_metadata` recursively redacts IBANs, supplier/contact info, and is reused for AI contexts and API responses (`app/utils/masking.py`).

### I.2 AI integration into proof flows
- Photo proofs: after geofence/EXIF validations, AI is invoked only when `ai_enabled()` is true, contexts include sanitized metadata, and failures fall back without blocking approvals (`app/services/proofs.py`).
- Document proofs: metadata is copied, stripped of client-provided `ai_assessment`, optionally enriched via OCR, backend checks computed, and AI runs in advisory mode without auto-approving; reviewer decisions still required.
- AI outputs are stored both in proof metadata (`ai_assessment`) and columns (`ai_risk_level`, `ai_score`, `ai_flags`, `ai_explanation`, `ai_checked_at`, reviewer fields) for downstream analytics (`app/models/proof.py`, `app/schemas/proof.py`).

### I.3 OCR & backend_checks
- `enrich_metadata_with_invoice_ocr` copies metadata, conditionally calls provider stub, normalizes totals/currency/date/IBAN/supplier without overwriting existing keys, and logs exceptions without failing proofs (`app/services/invoice_ocr.py`).
- `compute_document_backend_checks` compares expected vs actual amount/currency, IBAN last4, invoice date ranges, and supplier names, returning structured results consumed by AI context (`app/services/document_checks.py`).
- Document proof AI contexts embed both OCR-enriched metadata and backend check signals, ensuring GPT receives structured cues rather than raw documents (`app/services/proofs.py`).

### I.4 AI/OCR-specific risks
| ID | Domain | Risk | Impact | Likelihood | Priority | Recommended fix |
| --- | --- | --- | --- | --- | --- | --- |
| AI-1 | AI toggles | Cached settings require restarts to change AI behavior, risking inconsistent enforcement across replicas. | Medium | Medium | P0 | Refresh settings per request or memoize with TTL; add admin endpoint to flip AI flags with audit logging.
| AI-2 | OCR visibility | OCR stub returns `{}` silently and metadata lacks `ocr_status`, so reviewers may assume OCR ran when disabled. | Medium | Medium | P1 | Record `ocr_status` + provider metadata, emit metrics, and display status in reviewer UI/API.
| AI-3 | Metadata whitelist | Masking uses blacklist approach; new metadata keys could leak PII until explicitly added. | Medium | Low | P1 | Introduce whitelist serializer for proof metadata + regression tests for every new sensitive key.

## J. Roadmap to a staging-ready MVP
- **P0 checklist**
  1. Enforce non-null escrow deposit idempotency keys via migration/backfill to close remaining double-credit vector (R1).
  2. Implement PSP secret reload/alerting so operators detect missing/rotated secrets without restarts; expose metric for monitoring (R2).
  3. Emit `AuditLog` entries for all sensitive reads (transactions, payments, mandates, alerts) mirroring escrow read coverage (R3).
  4. Add scheduler leader guard (DB advisory lock or distributed store) and disable jobs when lock unavailable; surface status via `/health` (R4).
  5. Refactor AI/OCR flag helpers to re-evaluate settings per request or TTL cache plus admin toggle endpoint, ensuring consistent AI governance (R5/AI-1).

- **P1 checklist**
  - Surface OCR status/provider metadata and integrate at least one staging OCR provider so reviewers know when backend checks include OCR (R6/AI-2).
  - Add `pytest-asyncio` (or anyio) to re-enable skipped async scope test and extend coverage for new audit/idempotency behavior (R7).
  - Enhance `/health` with DB connectivity/migration drift checks and expose metrics for AI/OCR fallbacks.

- **P2 checklist**
  - Add admin endpoints for toggling AI/OCR flags, rotating PSP secrets, and inspecting scheduler status with audit trails.
  - Emit Prometheus metrics for AI fallbacks, OCR failures, PSP webhook latency, escrow deposit retries, and scheduler lock status.
  - Provide paginated exports for proofs/payments with masked metadata for compliance teams.

**Verdict: NO-GO for a staging with 10 real users** until P0 items (escrow DB idempotency, PSP secret observability, comprehensive read auditing, scheduler guardrails, AI toggle governance) are delivered. After these fixes and async tests are restored, the platform can safely onboard 5–10 staging users assuming a single runner and correctly configured secrets.

## K. Verification evidence
- `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` — succeeded (tail shown in `4b5182`).
- `alembic upgrade head` — applied all migrations successfully (`6f2591`).
- `alembic current` — reported `1b7cc2cfcc6e (head)` (`747d63`).
- `alembic heads` — single head `1b7cc2cfcc6e` (`3d0788`).
- `alembic history --verbose` — printed full linear chain through AI review fields (`f0b8b1`).
- `pytest -q` — `74 passed, 1 skipped, 2 warnings` (`d9314a`).
- Key `rg`/code excerpts referenced in sections above: e.g., `app/routers/escrow.py` lines 19–93 (endpoint auth/idempotency), `app/services/escrow.py` lines 104–205 (deposit validation + audit), `app/services/proofs.py` lines 51–210 (validation/AI), `app/services/ai_proof_advisor.py` lines 207–343 (context masking & fallbacks), `app/utils/masking.py` lines 6–110 (metadata masking), `app/services/document_checks.py` lines 24–155 (backend checks), `app/services/invoice_ocr.py` lines 12–113 (OCR enrichment), and `app/routers/psp.py` lines 20–60 plus `app/services/psp_webhooks.py` lines 25–147 (webhook security).
