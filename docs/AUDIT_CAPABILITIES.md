# Kobatela_alpha — Capability & Stability Audit (2025-02-15)

## A. Executive summary
- **Runtime configuration now refreshes via TTL caching and exposes AI/OCR/PSP flags over `/health`, so operators can verify rotations without redeploying and see scheduler state in one call.**【F:app/config.py†L32-L128】【F:app/routers/health.py†L1-L23】
- **Proof ingestion chains deterministic EXIF/geofence validation, invoice OCR enrichment, Decimal-safe backend checks, and AI advisory calls, storing AI outcomes on dedicated columns for reviewers.**【F:app/services/proofs.py†L51-L349】【F:app/services/invoice_ocr.py†L17-L134】【F:app/services/document_checks.py†L36-L169】【F:app/services/ai_proof_advisor.py†L237-L357】【F:app/models/proof.py†L15-L37】
- **PSP webhooks enforce rotating HMAC secrets, timestamp skew limits, and idempotent event storage before touching payment state.**【F:app/routers/psp.py†L19-L61】【F:app/services/psp_webhooks.py†L23-L188】
- **Escrow, payment, spend, and usage models all rely on Numeric(18,2) columns plus shared idempotency helpers, protecting against double credits and rounding drift.**【F:app/models/escrow.py†L23-L68】【F:app/models/payment.py†L21-L40】【F:app/models/spend.py†L13-L134】【F:app/services/idempotency.py†L12-L51】
- **Audit logging, metadata masking, and AI-governance requirements (e.g., note required before approving AI-flagged proofs) provide a consistent compliance backbone.**【F:app/utils/audit.py†L12-L107】【F:app/utils/masking.py†L6-L112】【F:app/services/proofs.py†L275-L399】

Major risks / limitations:
- **`Proof` metadata stores monetary comparisons in schemaless JSON, so mismatched Decimal scaling could reintroduce rounding gaps despite improved OCR normalization (P0 monetary safety).**【F:app/models/proof.py†L15-L37】【F:app/services/proofs.py†L67-L135】
- **Module-level `settings = get_settings()` instances (e.g., in `app/main.py`) bypass the TTL refresh, meaning PSP/AI secret rotations can still lag indefinitely for already-imported modules (P0 PSP governance).**【F:app/main.py†L21-L122】【F:app/config.py†L91-L128】
- **Sensitive read endpoints beyond `/users/{id}` (escrow, proofs, payments) still omit `AuditLog` writes, limiting lifecycle forensics (P0 business audit).**【F:app/routers/escrow.py†L86-L93】【F:app/routers/payments.py†L18-L22】
- **Scheduler locking now evicts stale rows after 10 minutes but lacks owner identifiers or heartbeat metrics, so a wedged job can silently pause mandate expiry (P0 lifecycle).**【F:app/services/scheduler_lock.py†L15-L70】【F:app/main.py†L58-L95】
- **AI/OCR telemetry is surfaced, yet the privacy layer still trusts upstream metadata and does not redact new keys by default, risking leakage into AI prompts or responses (P0 AI/OCR governance).**【F:app/services/ai_proof_advisor.py†L268-L357】【F:app/services/invoice_ocr.py†L102-L134】【F:app/utils/masking.py†L6-L112】

Readiness score: **74 / 100** — Core flows are production-grade, but the remaining P0 governance gaps must be closed before onboarding external pilots.

## B. Capability map (current features)
### B.1 Functional coverage
| Feature | Endpoints / modules involved | Status (OK / Partial / Missing) | Notes |
| --- | --- | --- | --- |
| Health & runtime introspection | `/health`, runtime flags (`is_scheduler_active`) | Partial | Reports PSP/AI/OCR flags and scheduler booleans but no DB/alembic drift check or AI/OCR error counters.【F:app/routers/health.py†L1-L23】【F:app/core/runtime_state.py†L1-L13】 |
| User & API key lifecycle | `/users`, `/apikeys` routers, audit helpers | Partial | User CRUD now logs reads, but list/search endpoints and API key pagination remain absent.【F:app/routers/users.py†L17-L80】【F:app/routers/apikeys.py†L63-L175】 |
| Escrow lifecycle | `/escrows/*`, escrow & payment services | OK | Supports creation, deposits with `Idempotency-Key`, delivery approval/rejection, and reads with scope enforcement.【F:app/routers/escrow.py†L19-L93】【F:app/services/payments.py†L18-L205】 |
| Mandates & spend controls | `/mandates`, `/spend/*`, usage services | OK | Mandates plus spend endpoints gate on scopes and idempotency; tests assert limit enforcement and idempotent spends.【F:app/routers/mandates.py†L13-L32】【F:app/routers/spend.py†L34-L178】【F:tests/test_spend_idempotency.py†L1-L88】 |
| Proof submission & AI advisory | `/proofs`, proof service, AI modules | OK | Photo proofs validate EXIF/geofence, documents trigger OCR + backend checks, and AI writes advisory metadata + columns with governance rules.【F:app/routers/proofs.py†L24-L54】【F:app/services/proofs.py†L67-L349】【F:app/services/ai_proof_advisor.py†L237-L357】 |
| Payments & PSP integration | `/payments/execute/{id}`, `/psp/webhook`, PSP service | Partial | Manual execute + webhook settlement exist, but no GET/list endpoints and PSP secret rotation still limited by module-level caching.【F:app/routers/payments.py†L18-L22】【F:app/routers/psp.py†L19-L61】【F:app/main.py†L21-L122】 |
| Transactions/allowlist/compliance | `/allowlist`, `/certified`, `/transactions*` | Partial | Admin-only flows exist with idempotency, but GET/list operations lack pagination and allowlist reads are missing.【F:app/routers/transactions.py†L25-L120】 |
| Alerts & monitoring | `/alerts` router | OK | Lists alerts filtered by type with admin/support scopes.【F:app/routers/alerts.py†L1-L25】 |
| AI & OCR toggles | `ai_proof_flags`, `invoice_ocr` services | Partial | Dynamic getters respect TTL, but metadata masking is best-effort and there are no Prometheus counters for AI/OCR fallbacks yet.【F:app/services/ai_proof_flags.py†L1-L31】【F:app/services/invoice_ocr.py†L17-L134】 |

### B.2 End-to-end journeys supported today
- **Photo proof auto-approve:** `/proofs` -> `submit_proof` validates EXIF/geofence, optionally calls AI, and can auto-approve milestones to trigger payouts via payments service.【F:app/routers/proofs.py†L24-L54】【F:app/services/proofs.py†L67-L349】
- **Invoice proof with OCR + backend checks:** Document proofs enrich metadata via OCR, compute backend comparisons, and forward sanitized context to AI for reviewer hints.【F:app/services/invoice_ocr.py†L17-L134】【F:app/services/document_checks.py†L36-L169】【F:app/services/ai_proof_advisor.py†L237-L357】
- **Usage spend with idempotent payouts:** `/spend` enforces `Idempotency-Key`, allowlist policies, and reuses payments on retries as covered by spend idempotency tests.【F:app/routers/spend.py†L75-L178】【F:tests/test_spend_idempotency.py†L1-L88】
- **PSP settlement lifecycle:** `/psp/webhook` validates signatures, persists events, and calls payment settlement/failure handlers with audit logs.【F:app/routers/psp.py†L19-L61】【F:app/services/psp_webhooks.py†L102-L188】
- **Admin credentialing:** `/apikeys` + `/users` pair handles privileged onboarding with scope enforcement and audit logging for create/read actions.【F:app/routers/apikeys.py†L63-L175】【F:app/routers/users.py†L17-L80】

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request model | Response model | HTTP codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/health` | `health.healthcheck`【F:app/routers/health.py†L1-L23】 | None | – | – | dict | 200 |
| POST | `/users` | `users.create_user`【F:app/routers/users.py†L17-L53】 | API key | admin/support | `UserCreate` | `UserRead` | 201, 400 |
| GET | `/users/{user_id}` | `users.get_user`【F:app/routers/users.py†L55-L80】 | API key | admin/support | – | `UserRead` | 200, 404 |
| POST | `/apikeys` | `apikeys.create_api_key`【F:app/routers/apikeys.py†L63-L115】 | API key | admin | `CreateKeyIn` | `ApiKeyCreateOut` | 201, 400 |
| GET | `/apikeys/{api_key_id}` | `apikeys.get_apikey`【F:app/routers/apikeys.py†L117-L130】 | API key | admin | – | `ApiKeyRead` | 200, 404 |
| DELETE | `/apikeys/{api_key_id}` | `apikeys.revoke_apikey`【F:app/routers/apikeys.py†L132-L175】 | API key | admin | – | – | 204, 404 |
| POST | `/mandates` | `mandates.create_mandate`【F:app/routers/mandates.py†L13-L25】 | API key | sender | `UsageMandateCreate` | `UsageMandateRead` | 201 |
| POST | `/mandates/cleanup` | `mandates.cleanup_expired_mandates`【F:app/routers/mandates.py†L27-L32】 | API key | sender | – | `{expired}` | 202 |
| POST | `/escrows` | `escrow.create_escrow`【F:app/routers/escrow.py†L19-L27】 | API key | sender | `EscrowCreate` | `EscrowRead` | 201 |
| POST | `/escrows/{id}/deposit` | `escrow.deposit`【F:app/routers/escrow.py†L29-L41】 | API key | sender | `EscrowDepositCreate` + `Idempotency-Key` | `EscrowRead` | 200 |
| POST | `/escrows/{id}/mark-delivered` | `escrow.mark_delivered`【F:app/routers/escrow.py†L43-L52】 | API key | sender | `EscrowActionPayload` | `EscrowRead` | 200 |
| POST | `/escrows/{id}/client-approve` | `escrow.client_approve`【F:app/routers/escrow.py†L54-L63】 | API key | sender | optional payload | `EscrowRead` | 200 |
| POST | `/escrows/{id}/client-reject` | `escrow.client_reject`【F:app/routers/escrow.py†L65-L74】 | API key | sender | optional payload | `EscrowRead` | 200 |
| POST | `/escrows/{id}/check-deadline` | `escrow.check_deadline`【F:app/routers/escrow.py†L76-L84】 | API key | sender | – | `EscrowRead` | 200 |
| GET | `/escrows/{id}` | `escrow.read_escrow`【F:app/routers/escrow.py†L86-L93】 | API key | sender/support/admin | – | `EscrowRead` | 200, 404 |
| POST | `/proofs` | `proofs.submit_proof`【F:app/routers/proofs.py†L24-L35】 | API key | sender | `ProofCreate` | `ProofRead` | 201, 404, 409, 422 |
| POST | `/proofs/{proof_id}/decision` | `proofs.decide_proof`【F:app/routers/proofs.py†L37-L54】 | API key | support/admin | `ProofDecision` | `ProofRead` | 200, 400, 404 |
| POST | `/spend/categories` | `spend.create_category`【F:app/routers/spend.py†L34-L46】 | API key | admin/support | `SpendCategoryCreate` | `SpendCategoryRead` | 201 |
| POST | `/spend/merchants` | `spend.create_merchant`【F:app/routers/spend.py†L48-L60】 | API key | admin/support | `MerchantCreate` | `MerchantRead` | 201 |
| POST | `/spend/allow` | `spend.allow_usage`【F:app/routers/spend.py†L62-L73】 | API key | admin/support | `AllowedUsageCreate` | dict | 201 |
| POST | `/spend/allowed` | `spend.add_allowed_payee`【F:app/routers/spend.py†L100-L134】 | API key | admin/support | `AddPayeeIn` | dict | 201 |
| POST | `/spend/purchases` | `spend.create_purchase`【F:app/routers/spend.py†L75-L98】 | API key | sender/admin | `PurchaseCreate` + `Idempotency-Key` | `PurchaseRead` | 201, 400, 403, 404, 409 |
| POST | `/spend` | `spend.spend`【F:app/routers/spend.py†L137-L178】 | API key | sender/admin | `SpendIn` + `Idempotency-Key` | dict | 200, 400, 403, 404 |
| POST | `/allowlist` | `transactions.add_to_allowlist`【F:app/routers/transactions.py†L25-L38】 | API key | admin | `AllowlistCreate` | dict | 201 |
| POST | `/certified` | `transactions.add_certification`【F:app/routers/transactions.py†L40-L53】 | API key | admin | `CertificationCreate` | dict | 201 |
| POST | `/transactions` | `transactions.post_transaction`【F:app/routers/transactions.py†L55-L90】 | API key | admin | `TransactionCreate` + `Idempotency-Key` | `TransactionRead` | 201, 400 |
| GET | `/transactions/{transaction_id}` | `transactions.get_transaction`【F:app/routers/transactions.py†L93-L120】 | API key | admin | – | `TransactionRead` | 200, 404 |
| POST | `/payments/execute/{payment_id}` | `payments.execute_payment`【F:app/routers/payments.py†L18-L22】 | API key | sender | path id | `PaymentRead` | 200, 404 |
| GET | `/alerts` | `alerts.list_alerts`【F:app/routers/alerts.py†L12-L25】 | API key | admin/support | query `type` | list[`AlertRead`] | 200 |
| POST | `/psp/webhook` | `psp.psp_webhook`【F:app/routers/psp.py†L19-L61】 | Signature | PSP | raw JSON | dict | 200, 401, 503 |

## D. Data model & state machines
- **Entities & constraints:**
  - **User / ApiKey:** Unique username/email and hashed API keys with scopes and audit logging on use.【F:app/models/user.py†L8-L22】【F:app/models/api_key.py†L1-L60】【F:app/security.py†L20-L155】
  - **EscrowAgreement / EscrowDeposit / EscrowEvent:** Numeric(18,2) totals, deposit idempotency keys, and timeline JSON payloads referencing users via FKs.【F:app/models/escrow.py†L23-L68】
  - **Milestone:** Indexed per-escrow sequence, Numeric amounts, JSON `proof_requirements`, and optional geofence floats for photo proofs.【F:app/models/milestone.py†L32-L62】
  - **Proof:** Unique SHA-256, JSON metadata, AI governance columns (`ai_risk_level`, `ai_score`, `ai_flags`, `ai_explanation`, `ai_checked_at`, `ai_reviewed_*`).【F:app/models/proof.py†L15-L37】
  - **Payment:** Numeric amounts with status enum + idempotency key indexes to protect payouts.【F:app/models/payment.py†L21-L40】
  - **UsageMandate / AllowedUsage / Purchase:** Numeric totals & statuses for spend governance with unique merchant/category constraints.【F:app/models/usage_mandate.py†L30-L66】【F:app/models/spend.py†L13-L134】
  - **PSPWebhookEvent / AuditLog / SchedulerLock:** Idempotent PSP events, centralized audit rows, and TTL lock rows for APScheduler.【F:app/models/psp_webhook.py†L10-L25】【F:app/models/audit.py†L10-L20】【F:app/models/scheduler_lock.py†L10-L17】

- **State machines:**
  - **Escrow lifecycle:** Escrow agreements move from DRAFT to FUNDED when deposits accumulate, to RELEASABLE upon proof approvals, and to RELEASED/REFUNDED via payment handlers that enforce Numeric balances.【F:app/models/escrow.py†L23-L68】【F:app/services/payments.py†L18-L205】
  - **Milestone/proof:** Milestones start WAITING, progress to PENDING_REVIEW when `submit_proof` stores metadata, and end in APPROVED/REJECTED via decision endpoint with AI note enforcement for warnings.【F:app/models/milestone.py†L21-L62】【F:app/services/proofs.py†L51-L399】
  - **Payments:** Payments transition PENDING→SENT→SETTLED/ERROR via manual execution and PSP webhooks; idempotency keys prevent double-sends.【F:app/models/payment.py†L11-L40】【F:app/services/psp_webhooks.py†L102-L188】

## E. Stability results
- **Static view of tests (not executed):** Suites span AI configs (`tests/test_ai_config.py`), AI privacy masking and proof responses (`tests/test_ai_privacy.py`), invoice OCR enrichment (`tests/test_invoice_ocr.py`), Decimal backend checks (`tests/test_document_checks.py`), PSP webhooks (`tests/test_psp_webhook.py`), scheduler locking (`tests/test_scheduler_lock.py`), spend idempotency (`tests/test_spend_idempotency.py`), escrow/milestone/payment flows, RBAC, and legacy key handling. Observations are from file inspection only; commands such as `pytest -q` were **not executed** per instructions.【F:tests/test_ai_config.py†L1-L24】【F:tests/test_ai_privacy.py†L10-L92】【F:tests/test_invoice_ocr.py†L1-L63】【F:tests/test_document_checks.py†L1-L27】【F:tests/test_psp_webhook.py†L1-L169】【F:tests/test_scheduler_lock.py†L1-L11】【F:tests/test_spend_idempotency.py†L1-L88】
- **Skipped/xfail markers:** None observed during static reading.
- **Static review notes:**
  - Health tests still expect `psp_webhook_secret_status`, yet the router now returns `psp_webhook_configured`, so the suite will fail without updates.【F:tests/test_health.py†L4-L12】【F:app/routers/health.py†L11-L23】
  - `transactions.post_transaction` duplicates the idempotency check block, indicating copy/paste debt but no functional break today.【F:app/routers/transactions.py†L55-L90】
  - OCR/AI services wrap exceptions and log fallbacks, but there are no metrics for failure counts, complicating alerting on AI degradation.【F:app/services/ai_proof_advisor.py†L245-L357】【F:app/services/invoice_ocr.py†L102-L134】
  - Scheduler lock TTL eviction works only on acquisition attempts; a long-running job still lacks a heartbeat to renew ownership.【F:app/services/scheduler_lock.py†L15-L70】

## F. Security & integrity
- **AuthN/Z:** API key extraction accepts Authorization or `X-API-Key`, validates hashes, enforces scopes per router, and logs each use to `AuditLog`. Legacy dev keys are gated by environment flags.【F:app/security.py†L20-L155】
- **Input validation & idempotency:** Pydantic schemas impose regex/length rules (e.g., `ProofDecision`, `AddPayeeIn`), and required `Idempotency-Key` headers guard POSTs for deposits, spend, purchases, and transactions; helper functions fetch/create idempotent rows atomically.【F:app/routers/spend.py†L75-L178】【F:app/routers/transactions.py†L55-L90】【F:app/services/idempotency.py†L12-L51】
- **File / proof validation:** Photo proofs enforce EXIF timestamps, GPS radius (Haversine), and hard error codes before any state change; document proofs compute backend checks covering amount, currency, IBAN last4, dates, and supplier names.【F:app/services/proofs.py†L67-L235】【F:app/services/document_checks.py†L36-L169】
- **Secret management:** `.env.example` documents PSP/AI/OCR env vars, AI + OCR default to disabled, and startup halts when PSP secrets are missing; TTL caching reloads settings every minute but module-level globals still cache values indefinitely.【F:.env.example†L1-L25】【F:app/main.py†L21-L82】【F:app/config.py†L91-L128】
- **Audit/logging:** Proof submissions, API key usage, PSP failures, and now `/users/{id}` reads write masked `AuditLog` entries, yet other high-risk reads (e.g., escrow/payment fetches) still lack audit coverage.【F:app/utils/audit.py†L12-L107】【F:app/routers/users.py†L17-L80】【F:app/routers/escrow.py†L86-L93】【F:app/routers/payments.py†L18-L22】

## G. Observability & operations
- **Logging:** `setup_logging()` executes during lifespan startup, and exception handlers capture both HTTP and generic exceptions with structured payloads; APScheduler emits warnings when multiple runners contend for the lock.【F:app/main.py†L26-L138】
- **HTTP error handling:** Shared `error_response` payloads standardize 4xx/5xx JSON, and PSP routes provide reason codes for signature failures.【F:app/utils/errors.py†L1-L40】【F:app/routers/psp.py†L19-L61】
- **Alembic migrations:** History covers AI proof columns, milestone proof requirements, and scheduler lock tables; operators should run `alembic upgrade head`, `alembic current`, `alembic heads`, and `alembic history --verbose` before deploys to confirm no drift. Commands were **not executed**; conclusions derive from reading migration files.【F:alembic/versions/013024e16da9_add_ai_fields_to_proofs.py†L1-L47】【F:alembic/versions/9c697d41f421_add_proof_requirements_to_milestones.py†L1-L27】【F:alembic/versions/a9bba28305c0_add_scheduler_locks_table.py†L1-L29】
- **Deployment specifics:** Lifespan gating ensures DB init + PSP secret validation before serving, and APScheduler is optional per `SCHEDULER_ENABLED`. There is still no automated DB health probe or schema checksum in `/health`.【F:app/main.py†L26-L138】【F:app/routers/health.py†L1-L23】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority (P0/P1/P2) | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Proof metadata / monetary safety | Monetary comparisons for invoices remain JSON-only; nothing enforces Numeric precision once stored, so upstream floats could reappear despite Decimal normalization. | False approvals/rejections or payout leakage | Medium | P0 | Add normalized `invoice_total_amount`/`invoice_currency` Numeric columns on `proofs`, backfill via migration, and hydrate them in `submit_proof` to guarantee Decimal math end-to-end (~0.5 day).【F:app/models/proof.py†L15-L37】【F:app/services/proofs.py†L67-L135】 |
| R2 | PSP webhook secret rotation | TTL caching reloads settings, but modules holding `settings = get_settings()` (e.g., `app/main.py`) never refresh, so PSP secret rotations can silently fail for running processes. | Webhook spoofing or settlement outage during rotation | High | P0 | Replace module-level globals with per-request `get_settings()` or inject settings via FastAPI dependencies; add Prometheus counters exposing active secret fingerprints (~1 day).【F:app/main.py†L21-L122】【F:app/config.py†L91-L128】 |
| R3 | Business lifecycle audit | Only some sensitive reads log audits; escrow, proof, and payment GETs return PII without `AuditLog` entries, hindering investigations. | Limited forensic trail for disputes | Medium | P0 | Instrument remaining read endpoints (escrow, proofs, payments, spend) with `actor_from_api_key` + `log_audit`, and document actor naming (~0.5 day).【F:app/routers/escrow.py†L86-L93】【F:app/routers/payments.py†L18-L22】 |
| R4 | Scheduler lifecycle resilience | TTL eviction happens only when `try_acquire_scheduler_lock` runs, and there is no owner field or heartbeat; a busy/failed scheduler may hold the lock for 10 minutes without monitoring. | Mandate cleanup pauses unnoticed | Medium | P0 | Extend `scheduler_locks` with `owner_id` and `expires_at`, refresh heartbeat periodically, and expose lock owner/age on `/health` (~1 day).【F:app/services/scheduler_lock.py†L15-L70】【F:app/core/runtime_state.py†L1-L13】 |
| R5 | AI/OCR data governance | Masking is allowlist-based and OCR metadata is copied verbatim unless collisions occur; new keys (e.g., `supplier_tax_id`) could leak into AI prompts or client responses. | PII leakage to LLM or API consumer | Medium | P0 | Move to schema-driven allowlists per proof type, mask unknown keys by default, and add tests covering new OCR fields (~1 day).【F:app/services/invoice_ocr.py†L47-L134】【F:app/utils/masking.py†L6-L112】 |
| R6 | Health telemetry debt | `/health` omits DB/alembic checks and mismatch with tests indicates drift between runtime payload and observability expectations. | Missed early warning on migration drift | Medium | P1 | Add DB ping + Alembic head hash to `/health`, then align tests to new schema (~0.5 day).【F:app/routers/health.py†L11-L23】【F:tests/test_health.py†L4-L12】 |
| R7 | PSP webhook idempotency logging | PSP handler logs successes but not per-payment audit entries, so settlement vs. failure context lives only in logs. | Harder PSP reconciliation | Low | P2 | Write `AuditLog` rows on `_mark_payment_settled/_mark_payment_error` with sanitized payloads (~0.25 day).【F:app/services/psp_webhooks.py†L133-L187】 |

## I. AI Proof Advisor, OCR & risk scoring (dedicated section)
### I.1 AI architecture
- Configuration lives in `Settings` with AI disabled by default, explicit provider/model/timeout, and `.env.example` documents each flag plus optional OpenAI key.【F:app/config.py†L32-L128】【F:.env.example†L10-L25】
- Flag helpers call `get_settings()` per access, so toggles follow TTL refreshes; dedicated helpers expose provider, model, and timeout values.【F:app/services/ai_proof_flags.py†L1-L31】
- AI stack modules include `ai_proof_flags` (feature gating), `ai_proof_advisor` (OpenAI integration), `document_checks` (backend comparisons), and `invoice_ocr` (metadata enrichment before AI).【F:app/services/ai_proof_advisor.py†L237-L357】【F:app/services/document_checks.py†L36-L169】【F:app/services/invoice_ocr.py†L17-L134】

### I.2 AI integration into proof flows
- `submit_proof` strips client-provided `ai_assessment`, enriches metadata for documents, runs backend checks, and only then calls AI (photo proofs also validate EXIF/geo first). AI responses update DB columns and metadata; auto-approval stays gated by hard validations and AI decisions remain advisory.【F:app/services/proofs.py†L67-L349】
- `call_ai_proof_advisor` short-circuits when `ai_enabled()` is false or the API key/sdk is missing, returning fallback warnings rather than failing the proof; any exception logs and yields a warning response with `ai_unavailable` flags.【F:app/services/ai_proof_advisor.py†L237-L357】
- Read schemas mask metadata before returning to clients, so AI results (risk level, score, flags, explanation) are observable but write-protected; clients cannot set AI fields via `ProofCreate`.【F:app/schemas/proof.py†L16-L44】
- Approving AI-flagged proofs requires a manual note, ensuring humans stay in the loop even if AI says “warning/suspect.”【F:app/services/proofs.py†L353-L399】

### I.3 OCR & backend_checks
- OCR calls depend on `INVOICE_OCR_ENABLED/PROVIDER`; disabled states set metadata `ocr_status=disabled` without touching other keys. Successful calls normalize totals with Decimal quantization, uppercase currencies, keep raw totals, and only append fields when absent. Errors mark `ocr_status=error` but never raise. Metadata also records `ocr_provider`.【F:app/services/invoice_ocr.py†L17-L134】
- `compute_document_backend_checks` converts all numeric inputs to Decimal, computes absolute/relative differences, compares currency/IBAN/date/supplier, and returns structured dicts even when some data is missing. Outputs feed AI context via `backend_checks`.【F:app/services/document_checks.py†L36-L169】
- Tests cover disabled OCR, provider success, metadata non-overwrite, and Decimal comparisons to guard regressions.【F:tests/test_invoice_ocr.py†L20-L63】【F:tests/test_document_checks.py†L6-L27】

### I.4 AI/OCR-specific risks
| ID | Domain (AI/OCR) | Risk | Impact | Likelihood | Priority | Recommended fix |
| --- | --- | --- | --- | --- | --- | --- |
| AI-1 | AI governance | Masking allowlist may miss new metadata keys introduced by OCR/providers, leaking PII to OpenAI or clients. | Regulatory/privacy breach | Medium | P0 | Enforce schema-based allowlists and fail safe (mask unknown keys) before building AI prompts.【F:app/services/ai_proof_advisor.py†L268-L357】【F:app/utils/masking.py†L6-L112】 |
| AI-2 | AI observability | No Prometheus counters/alerts for AI fallbacks, so ops cannot detect failing providers quickly. | Silent AI outages | Medium | P1 | Emit metrics (`ai_proof_fallback_total`, `ai_enabled`) and expose them on `/metrics` when Prometheus is enabled.【F:app/services/ai_proof_advisor.py†L245-L357】【F:app/main.py†L102-L121】 |
| AI-3 | OCR source of truth | OCR-normalized values never overwrite existing metadata, but there is no flag to indicate stale/mismatching data besides `backend_checks`; reviewers may miss when OCR disagrees with provided totals. | Reviewer confusion | Low | P2 | Surface backend check outcomes in API responses/alerts and require manual acknowledgement before approval when mismatches exist.【F:app/services/proofs.py†L67-L235】【F:app/services/document_checks.py†L36-L169】 |
| AI-4 | Privacy in AI prompts | `call_ai_proof_advisor` logs warnings when disabled but still builds sanitized context via JSON dumps; if serialization fails, context becomes `{}` silently. | Lost explainability | Low | P2 | Add validation + tests ensuring essential context fields survive masking, otherwise raise structured warnings surfaced to reviewers.【F:app/services/ai_proof_advisor.py†L207-L357】 |

**Tests to add:**
1. Ensure `/health` exposes live `ai_proof_enabled` and `ocr_enabled` flags when toggles change mid-process (monkeypatch `get_settings`).
2. Simulate OCR returning `supplier_tax_id` to verify `mask_proof_metadata` masks unknown sensitive keys before AI context is built.
3. Unit-test fallback path when AI raises `json.JSONDecodeError`, confirming `ai_flags` include `exception_during_call` and metadata stores the fallback.
4. Add regression test verifying backend amount differences propagate into AI context and onto the proof record for reviewer consumption.

## J. Roadmap to a staging-ready MVP
- **P0 checklist (blockers):**
  1. Introduce Numeric invoice columns on `proofs` and hydrate them during submission to close the JSON monetary gap (R1).【F:app/models/proof.py†L15-L37】
  2. Remove global `settings` singletons (notably in `app/main.py`) so PSP secret rotations and AI toggles refresh immediately (R2).【F:app/main.py†L21-L122】
  3. Add audit logging to every PII-bearing read (escrow/proof/payment/spend) and document actor semantics (R3).【F:app/routers/escrow.py†L86-L93】【F:app/routers/payments.py†L18-L22】
  4. Extend scheduler lock with owner/heartbeat metadata and surface lock state on `/health` to avoid silent cron stalls (R4).【F:app/services/scheduler_lock.py†L15-L70】
  5. Default-mask unknown OCR metadata keys and add tests/metrics for AI fallbacks to meet privacy governance (R5).【F:app/services/invoice_ocr.py†L102-L134】【F:app/services/ai_proof_advisor.py†L245-L357】

- **P1 checklist (pre-pilot hardening):**
  1. Align `/health` payload with tests and add DB/alembic drift probes (R6).【F:app/routers/health.py†L11-L23】【F:tests/test_health.py†L4-L12】
  2. Publish AI/OCR fallback counters to Prometheus and alert on spikes (AI-2).【F:app/services/ai_proof_advisor.py†L245-L357】
  3. Provide pagination for `/apikeys` and `/transactions` to avoid unbounded responses as data grows.【F:app/routers/apikeys.py†L63-L175】【F:app/routers/transactions.py†L25-L120】

- **P2 checklist (comfort & scalability):**
  1. Add GET endpoints for allowlist/certified records and PSP payment listings for better operator UX.【F:app/routers/transactions.py†L25-L90】【F:app/routers/payments.py†L18-L22】
  2. Implement actual OCR provider integration with deterministic sandbox responses, plus metadata fields for failure reasons.【F:app/services/invoice_ocr.py†L17-L134】
  3. Add structured correlation IDs/log context to tie proofs, payments, and audits together in logs.【F:app/main.py†L26-L138】

**Verdict: NO-GO for a staging with 10 real users** until P0 items (monetary enforcement, PSP rotation responsiveness, audit coverage, scheduler lock telemetry, AI/OCR privacy hardening) are closed. Once addressed, the existing architecture should support a limited pilot.

## K. Verification evidence
- **Migrations (conceptual):** `alembic upgrade head` would apply scheduler lock, AI proof, and milestone requirement migrations; `alembic current`/`alembic heads`/`alembic history --verbose` would confirm the linear chain spanning `013024e16da9`, `9c697d41f421`, and `a9bba28305c0`. This inference is based on inspecting the migration files listed earlier rather than executing Alembic commands.【F:alembic/versions/013024e16da9_add_ai_fields_to_proofs.py†L1-L47】【F:alembic/versions/9c697d41f421_add_proof_requirements_to_milestones.py†L1-L27】【F:alembic/versions/a9bba28305c0_add_scheduler_locks_table.py†L1-L29】
- **Test suite structure:** A hypothetical `pytest -q` would exercise AI configs/privacy, OCR/document checks, PSP webhooks, scheduler locks, spend idempotency, escrow/milestone/payment flows, BO RBAC, and health checks. This summary derives from the files enumerated in Section E; tests were not run per static-only mandate.【F:tests/test_ai_config.py†L1-L24】【F:tests/test_invoice_ocr.py†L1-L63】【F:tests/test_psp_webhook.py†L1-L169】
- **Key file references:** The citations embedded above point to specific files/lines (e.g., proof pipeline, AI advisor, OCR normalization, scheduler lock TTL), serving as the evidence base one would otherwise gather via `rg`/`grep` when validating code paths.
