# Kobatela_alpha — Capability & Stability Audit (2025-02-14)

## A. Executive summary
- API key auth is centralized in `require_api_key`/`require_scope`, logging every successful lookup (including legacy dev keys) so sensitive routers inherit consistent enforcement and audit breadcrumbs.【F:app/security.py†L19-L123】
- FastAPI's lifespan gate refuses to boot without configured PSP secrets, initializes logging/CORS/Prometheus/Sentry, and acquires a DB-backed scheduler lock before scheduling jobs, preventing partially configured instances from serving traffic.【F:app/main.py†L26-L138】
- Proof ingestion layers EXIF/geofence validation, optional invoice OCR enrichment, backend document checks, and masked AI advisory calls while persisting AI signals to dedicated columns for downstream reviewers.【F:app/services/proofs.py†L51-L350】【F:app/services/invoice_ocr.py†L16-L126】【F:app/services/document_checks.py†L24-L155】【F:app/services/ai_proof_advisor.py†L228-L343】【F:app/models/proof.py†L15-L37】
- PSP webhooks enforce rotating HMAC secrets plus timestamp skew limits, persist every event idempotently, and update payments/audit logs under strict status checks, reducing replay or forgery windows.【F:app/routers/psp.py†L19-L60】【F:app/services/psp_webhooks.py†L57-L188】【F:app/models/psp_webhook.py†L10-L25】
- Read schemas expose AI governance fields read-only, ensuring clients cannot tamper with `ai_risk_level` yet operators can reason about AI outcomes programmatically.【F:app/schemas/proof.py†L16-L44】

Major risks / limitations:
- Invoice OCR normalization casts totals to `float` and backend amount checks also downcast to float, so rounding errors can flag valid invoices or hide mismatches—a P0 monetary gap.【F:app/services/invoice_ocr.py†L38-L120】【F:app/services/document_checks.py†L43-L76】
- Settings are singletons cached at startup, so rotating PSP secrets or AI/OCR toggles requires a redeploy; mid-incident rotations cannot propagate, and stale values might continue verifying webhooks.【F:app/config.py†L32-L112】【F:app/services/ai_proof_flags.py†L6-L31】【F:app/services/psp_webhooks.py†L24-L99】
- Sensitive GETs such as `/users/{id}` return PII without writing `AuditLog` rows, weakening lifecycle forensics despite available helpers.【F:app/routers/users.py†L55-L68】【F:app/utils/audit.py†L78-L104】
- Scheduler locking inserts a single row with no TTL; a crash while holding the lock permanently disables background jobs until manual cleanup, risking expired mandates never closing.【F:app/services/scheduler_lock.py†L14-L51】【F:app/main.py†L63-L94】
- AI toggles simply read cached settings with no telemetry or per-request refresh, so partial deployments can disagree on policy without any signal to reviewers.【F:app/services/ai_proof_flags.py†L6-L31】

Readiness score: **72 / 100** — Architectural foundations are strong, but the P0 issues above must be resolved before inviting external pilot users.

## B. Capability map (current features)
### B.1 Functional coverage
| Feature | Endpoints / modules involved | Status (OK / Partial / Missing) | Notes |
| --- | --- | --- | --- |
| Health & runtime introspection | `/health`, runtime-state helpers (`is_scheduler_active`) | Partial | Exposes PSP secret status and scheduler flag but omits DB/alembic drift checks.【F:app/routers/health.py†L10-L26】【F:app/core/runtime_state.py†L7-L13】 |
| User & API key lifecycle | `/users`, `/apikeys` routers with audit helpers | Partial | Create paths audit actions, but user reads lack audit logging and key lists have no pagination.【F:app/routers/users.py†L17-L68】【F:app/routers/apikeys.py†L24-L175】 |
| Escrow lifecycle | `/escrows/*`, payout services | OK | Covers creation, deposits (with Idempotency-Key), mark delivered, approve/reject, reads, and payout hooks.【F:app/routers/escrow.py†L19-L93】【F:app/services/payments.py†L85-L205】 |
| Mandates & spend controls | `/mandates`, `/spend/*`, usage services/tests | OK | Mandates plus spend endpoints enforce scopes and idempotency; tests assert header requirements and replay safety.【F:app/routers/mandates.py†L13-L32】【F:app/routers/spend.py†L34-L178】【F:tests/test_spend_idempotency.py†L49-L88】 |
| Proof submission & AI advisory | `/proofs`, proof service, AI modules | OK | Photo proofs gate on EXIF/geo; document proofs add OCR + backend checks before AI writes advisory metadata/columns.【F:app/routers/proofs.py†L24-L54】【F:app/services/proofs.py†L67-L335】【F:app/services/ai_proof_advisor.py†L228-L343】 |
| Payments & PSP integration | `/payments/execute/{id}`, `/psp/webhook`, payments service | Partial | Manual execution API plus webhook settlement exist, but no GET/list endpoints and secrets are static until redeploy.【F:app/routers/payments.py†L11-L22】【F:app/routers/psp.py†L19-L60】【F:app/services/psp_webhooks.py†L57-L188】 |
| Transactions/allowlist/compliance | `/allowlist`, `/certified`, `/transactions*` | Partial | Supports allowlist/certification and idempotent transaction posts, yet GET lacks pagination and allowlist reads absent.【F:app/routers/transactions.py†L25-L120】 |
| Alerts & monitoring | `/alerts` | OK | Lists alerts with admin/support scopes and optional type filter.【F:app/routers/alerts.py†L12-L25】 |
| AI & OCR toggles | `ai_proof_flags`, `invoice_ocr` services | Partial | Flags default disabled and respect provider settings, but no dynamic reload or telemetry for operators.【F:app/services/ai_proof_flags.py†L6-L31】【F:app/services/invoice_ocr.py†L16-L126】 |

### B.2 End-to-end journeys supported today
- **Photo proof auto-approve**: `/proofs` -> `submit_proof` validates EXIF/geofence, optionally calls AI, auto-approves on clean signals, then triggers payout execution.【F:app/routers/proofs.py†L24-L54】【F:app/services/proofs.py†L67-L335】
- **Invoice proof with OCR + AI**: Document proof submission enriches metadata via OCR, runs backend amount/IBAN/date/supplier checks, and calls AI advisor with sanitized context for reviewers.【F:app/services/proofs.py†L71-L235】【F:app/services/invoice_ocr.py†L93-L126】【F:app/services/document_checks.py†L24-L155】
- **Usage spend with idempotent payouts**: `/spend` requires Idempotency-Key, checks allowlist + limits, and reuses payouts on duplicate headers as asserted in tests.【F:app/routers/spend.py†L137-L178】【F:tests/test_spend_idempotency.py†L49-L88】
- **PSP settlement lifecycle**: `/psp/webhook` verifies HMAC/timestamps, persists the event, and calls payment finalization or failure flows while logging outcomes.【F:app/routers/psp.py†L19-L60】【F:app/services/psp_webhooks.py†L101-L188】

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request model | Response model | HTTP codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/health` | `health.healthcheck`【F:app/routers/health.py†L10-L25】 | None | – | – | dict | 200 |
| POST | `/users` | `users.create_user`【F:app/routers/users.py†L17-L52】 | API key | admin/support | `UserCreate` | `UserRead` | 201, 400 |
| GET | `/users/{user_id}` | `users.get_user`【F:app/routers/users.py†L55-L68】 | API key | admin/support | – | `UserRead` | 200, 404 |
| POST | `/apikeys` | `apikeys.create_api_key`【F:app/routers/apikeys.py†L63-L115】 | API key | admin | `CreateKeyIn` | `ApiKeyCreateOut` | 201, 400 |
| GET | `/apikeys/{api_key_id}` | `apikeys.get_apikey`【F:app/routers/apikeys.py†L117-L129】 | API key | admin | – | `ApiKeyRead` | 200, 404 |
| DELETE | `/apikeys/{api_key_id}` | `apikeys.revoke_apikey`【F:app/routers/apikeys.py†L132-L175】 | API key | admin | – | – | 204, 404 |
| POST | `/mandates` | `mandates.create_mandate`【F:app/routers/mandates.py†L13-L25】 | API key | sender | `UsageMandateCreate` | `UsageMandateRead` | 201 |
| POST | `/mandates/cleanup` | `mandates.cleanup_expired_mandates`【F:app/routers/mandates.py†L27-L32】 | API key | sender | – | `{expired}` | 202 |
| POST | `/escrows` | `escrow.create_escrow`【F:app/routers/escrow.py†L19-L27】 | API key | sender | `EscrowCreate` | `EscrowRead` | 201 |
| POST | `/escrows/{escrow_id}/deposit` | `escrow.deposit` (+`Idempotency-Key`)【F:app/routers/escrow.py†L29-L40】 | API key | sender | `EscrowDepositCreate` | `EscrowRead` | 200, 400 |
| POST | `/escrows/{escrow_id}/mark-delivered` | `escrow.mark_delivered`【F:app/routers/escrow.py†L43-L52】 | API key | sender | `EscrowActionPayload` | `EscrowRead` | 200 |
| POST | `/escrows/{escrow_id}/client-approve` | `escrow.client_approve`【F:app/routers/escrow.py†L54-L63】 | API key | sender | optional `EscrowActionPayload` | `EscrowRead` | 200 |
| POST | `/escrows/{escrow_id}/client-reject` | `escrow.client_reject`【F:app/routers/escrow.py†L65-L74】 | API key | sender | optional payload | `EscrowRead` | 200 |
| POST | `/escrows/{escrow_id}/check-deadline` | `escrow.check_deadline`【F:app/routers/escrow.py†L76-L83】 | API key | sender | – | `EscrowRead` | 200 |
| GET | `/escrows/{escrow_id}` | `escrow.read_escrow`【F:app/routers/escrow.py†L86-L93】 | API key | sender/support/admin | – | `EscrowRead` | 200, 404 |
| POST | `/proofs` | `proofs.submit_proof`【F:app/routers/proofs.py†L24-L35】 | API key | sender | `ProofCreate` | `ProofRead` | 201, 404, 409, 422 |
| POST | `/proofs/{proof_id}/decision` | `proofs.decide_proof`【F:app/routers/proofs.py†L37-L54】 | API key | support/admin | `ProofDecision` | `ProofRead` | 200, 400, 404 |
| POST | `/spend/categories` | `spend.create_category`【F:app/routers/spend.py†L34-L46】 | API key | admin/support | `SpendCategoryCreate` | `SpendCategoryRead` | 201 |
| POST | `/spend/merchants` | `spend.create_merchant`【F:app/routers/spend.py†L48-L60】 | API key | admin/support | `MerchantCreate` | `MerchantRead` | 201 |
| POST | `/spend/allow` | `spend.allow_usage`【F:app/routers/spend.py†L62-L73】 | API key | admin/support | `AllowedUsageCreate` | dict | 201 |
| POST | `/spend/allowed` | `spend.add_allowed_payee`【F:app/routers/spend.py†L100-L134】 | API key | admin/support | `AddPayeeIn` | dict | 201 |
| POST | `/spend/purchases` | `spend.create_purchase` (+`Idempotency-Key`)【F:app/routers/spend.py†L75-L98】 | API key | sender/admin | `PurchaseCreate` | `PurchaseRead` | 201, 400, 403, 404, 409 |
| POST | `/spend` | `spend.spend` (+`Idempotency-Key`)【F:app/routers/spend.py†L137-L178】 | API key | sender/admin | `SpendIn` | dict | 200, 400, 403, 404 |
| POST | `/allowlist` | `transactions.add_to_allowlist`【F:app/routers/transactions.py†L25-L38】 | API key | admin | `AllowlistCreate` | dict | 201 |
| POST | `/certified` | `transactions.add_certification`【F:app/routers/transactions.py†L40-L53】 | API key | admin | `CertificationCreate` | dict | 201 |
| POST | `/transactions` | `transactions.post_transaction` (+`Idempotency-Key`)【F:app/routers/transactions.py†L55-L90】 | API key | admin | `TransactionCreate` | `TransactionRead` | 201, 400 |
| GET | `/transactions/{transaction_id}` | `transactions.get_transaction`【F:app/routers/transactions.py†L93-L120】 | API key | admin | – | `TransactionRead` | 200, 404 |
| POST | `/payments/execute/{payment_id}` | `payments.execute_payment`【F:app/routers/payments.py†L11-L22】 | API key | sender | path id | `PaymentRead` | 200, 404 |
| GET | `/alerts` | `alerts.list_alerts`【F:app/routers/alerts.py†L12-L25】 | API key | admin/support | query `type` | list[`AlertRead`] | 200 |
| POST | `/psp/webhook` | `psp.psp_webhook` (HMAC headers)【F:app/routers/psp.py†L19-L60】 | Signature | PSP | raw JSON | `{ok}` dict | 200, 401, 503 |

## D. Data model & state machines
| Entity | Key fields | Constraints / relationships | Source |
| --- | --- | --- | --- |
| User | `username`, `email`, `is_active` | Unique username/email, linked to transactions | 【F:app/models/user.py†L8-L22】 |
| ApiKey | `prefix`, `key_hash`, `scope`, `expires_at` | Unique prefix, scope enum, audit logging on use | 【F:app/models/api_key.py†L1-L60】【F:app/security.py†L19-L123】 |
| EscrowAgreement | `client_id`, `provider_id`, `amount_total`, `status`, `deadline_at` | Numeric(18,2) with non-negative check, JSON release conditions, relationships to deposits/events | 【F:app/models/escrow.py†L12-L68】 |
| EscrowDeposit | `escrow_id`, `amount`, `idempotency_key` | Positive amount, unique idempotency key | 【F:app/models/escrow.py†L45-L55】 |
| Milestone | `escrow_id`, `idx`, `amount`, `proof_type`, `proof_requirements`, geofence fields | Unique per escrow index, positive checks, optional geofence floats | 【F:app/models/milestone.py†L21-L62】 |
| Proof | `escrow_id`, `milestone_id`, `sha256`, `metadata`, `status`, AI fields (`ai_risk_level`, `ai_score`, `ai_flags`, `ai_explanation`, `ai_checked_at`, `ai_reviewed_by`, `ai_reviewed_at`) | Unique SHA-256, JSON metadata, timestamps for AI governance | 【F:app/models/proof.py†L10-L37】 |
| Payment | `escrow_id`, `milestone_id`, `amount`, `psp_ref`, `status`, `idempotency_key` | Numeric(18,2) amounts, indexes on status/idempotency | 【F:app/models/payment.py†L11-L40】 |
| UsageMandate | `sender_id`, `beneficiary_id`, `total_amount`, `currency`, `expires_at`, `status` | Numeric(18,2) totals, active lookup index, status enum | 【F:app/models/usage_mandate.py†L22-L66】 |
| AllowedUsage & Purchase | Merchant/category targeting, amount/currency, idempotency key | Mutually exclusive merchant/category constraint, Numeric(18,2) purchases | 【F:app/models/spend.py†L13-L83】 |
| PSPWebhookEvent | `event_id`, `psp_ref`, `kind`, `raw_json`, timestamps | Unique event ID and indexes for replay protection | 【F:app/models/psp_webhook.py†L10-L25】 |
| AuditLog | `actor`, `action`, `entity`, `data_json`, `at` | Centralized log table for compliance | 【F:app/models/audit.py†L10-L20】 |

State machines:
- **Escrow lifecycle**: Status transitions from DRAFT → FUNDED when deposits accumulate, to RELEASABLE when milestones approve, and RELEASED/REFUNDED via payment handlers; enforced by Numeric checks and payment post-handlers updating escrow events.【F:app/models/escrow.py†L12-L68】【F:app/services/payments.py†L85-L205】
- **Milestone & proof**: Milestones start WAITING, move to PENDING_REVIEW or APPROVED based on `submit_proof` auto-approve logic, and can be REJECTED via decision endpoint, requiring AI note overrides when warnings exist.【F:app/models/milestone.py†L21-L62】【F:app/services/proofs.py†L79-L399】
- **Payments**: `execute_payout` uses idempotency to reuse SENT/SETTLED payments, marks milestones PAID, and PSP webhooks finalize SETTLED/ERROR states; manual `/payments/execute` retries pending rows.【F:app/services/payments.py†L85-L205】【F:app/services/psp_webhooks.py†L132-L186】

## E. Stability results
- **Static view of tests (not executed)**: Test suites cover AI flags (`tests/test_ai_config.py`), AI privacy masking and proof response redaction (`tests/test_ai_privacy.py`), invoice OCR enrichment toggles (`tests/test_invoice_ocr.py`), AI reviewer note enforcement (`tests/test_proof_ai_review.py`), PSP webhooks/HMAC drift (`tests/test_psp_webhook.py`), spend idempotency headers (`tests/test_spend_idempotency.py`), scheduler lock exclusivity (`tests/test_scheduler_lock.py`), escrow flows, payments, mandates, and BO RBAC. All observations come from file inspection only; `pytest -q` was not run.【F:tests/test_ai_config.py†L1-L24】【F:tests/test_ai_privacy.py†L10-L92】【F:tests/test_invoice_ocr.py†L1-L41】【F:tests/test_proof_ai_review.py†L11-L100】【F:tests/test_psp_webhook.py†L1-L169】【F:tests/test_spend_idempotency.py†L1-L88】【F:tests/test_scheduler_lock.py†L1-L11】
- **Static review notes**: Invoice OCR and backend checks use floats, risking cent-level drift; settings caching blocks runtime rotations; `/users/{id}` lacks `AuditLog`; scheduler locks never expire; AI advisor wraps large `except Exception` blocks which are acceptable for resilience but hide telemetry, so metrics should flag AI fallback rates.【F:app/services/invoice_ocr.py†L38-L126】【F:app/services/document_checks.py†L43-L154】【F:app/config.py†L32-L112】【F:app/routers/users.py†L55-L68】【F:app/services/scheduler_lock.py†L14-L51】【F:app/services/ai_proof_advisor.py†L228-L343】

## F. Security & integrity
- **AuthN/Z**: API key extraction supports `Authorization` and `X-API-Key` headers, logs legacy key usage, and scopes routes via `require_scope`, enforcing least privilege per router (sender/support/admin).【F:app/security.py†L19-L123】【F:app/routers/spend.py†L34-L178】
- **Input validation & idempotency**: Pydantic schemas enforce bounds (e.g., `ProofDecision` regex, `SpendIn` decimals). Critical POSTs require `Idempotency-Key` headers, with shared helpers retrieving or creating rows to avoid double charges.【F:app/schemas/proof.py†L39-L44】【F:app/routers/transactions.py†L55-L90】【F:app/services/idempotency.py†L12-L51】
- **File/proof validation**: Photo proofs validate EXIF timestamps, GPS radius, and enforce hard 422 errors before state changes; document proofs compute deterministic amount/IBAN/date/supplier comparisons and store review reasons for manual flows.【F:app/services/proofs.py†L67-L235】【F:app/services/document_checks.py†L24-L155】
- **Secret management**: Settings defaults keep AI/OCR disabled and `.env.example` documents PSP/AI/OCR keys; startup aborts if secrets missing, yet runtime rotation still requires redeploy due to cached settings.【F:app/config.py†L32-L112】【F:.env.example†L1-L25】
- **Audit/logging**: Proof submissions/decisions, API key usage, PSP failures, and spend allowances write `AuditLog` entries with sanitized payloads, but user reads and some payment reads remain unaudited.【F:app/services/proofs.py†L274-L350】【F:app/services/psp_webhooks.py†L157-L186】【F:app/utils/audit.py†L12-L104】【F:app/routers/users.py†L55-L68】

## G. Observability & operations
- Logging is initialized at startup, wrappers catch generic and HTTP exceptions, and Prometheus/Sentry are optional via config flags; however, there are no structured correlation IDs or AI/OCR fallback metrics yet.【F:app/main.py†L26-L138】
- `/health` reports PSP secret status and scheduler activation but does not run DB queries or Alembic drift checks; extending it would provide earlier warning of schema mismatches.【F:app/routers/health.py†L10-L26】
- Alembic history includes AI proof columns and milestone proof requirements; manually reviewing `alembic/versions/*.py` confirms heads but commands like `alembic current` were not executed in this static audit.【F:alembic/versions/013024e16da9_add_ai_fields_to_proofs.py†L1-L47】【F:alembic/versions/1b7cc2cfcc6e_add_ai_review_fields_to_proofs.py†L1-L31】【F:alembic/versions/9c697d41f421_add_proof_requirements_to_milestones.py†L1-L27】
- Scheduler lock management simply inserts/deletes rows; if a runner dies, manual cleanup is required because no heartbeat or TTL exists, and `/health` only shows a boolean flag.【F:app/services/scheduler_lock.py†L14-L51】【F:app/core/runtime_state.py†L7-L13】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority (P0/P1/P2) | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Invoice OCR normalization | Float casting of totals introduces rounding errors before backend checks, misclassifying invoices or AI context. | Monetary mismatches and false fraud alerts | Medium | P0 | Normalize OCR amounts with `Decimal` (e.g., `Decimal(str(total))`), keep original string for audit, and add regression tests for >2 decimal values (~0.5 day).【F:app/services/invoice_ocr.py†L38-L90】【F:app/services/document_checks.py†L43-L76】 |
| R2 | PSP webhook secret rotation | `get_settings()` is cached, so rotating `psp_webhook_secret` or `_next` requires restarts; stale pods may reject or accept wrong signatures. | Settlement failures or spoofed acceptance | High | P0 | Implement a lightweight settings reloader/TTL cache or store secrets in the DB, plus expose hashed secret fingerprints via `/health` (~1 day).【F:app/config.py†L32-L112】【F:app/services/psp_webhooks.py†L24-L99】 |
| R3 | Business lifecycle audit | `/users/{id}` and similar reads do not log `AuditLog` entries, leaving no trace of PII access. | Compliance gaps and weaker investigations | Medium | P0 | Call `log_audit` with actor/entity metadata on sensitive GET endpoints and include this in reviewer playbooks (~0.5 day).【F:app/routers/users.py†L55-L68】【F:app/utils/audit.py†L78-L104】 |
| R4 | Scheduler lock resilience | Insert-only lock row without TTL sticks forever if a runner crashes while holding it, disabling mandate expiration jobs. | Mandates may never expire; payouts stall | Medium | P0 | Add `expires_at`/`owner_id` columns or switch to Postgres advisory locks; expose lock owner in `/health` and add cleanup job (~1 day).【F:app/services/scheduler_lock.py†L14-L51】【F:app/main.py†L63-L94】 |
| R5 | AI/OCR toggle governance | Flags read cached settings without metrics, so pods can diverge on AI policy with no alert. | Inconsistent AI enforcement & privacy risk | Medium | P0 | Refresh settings per request or add TTL caching plus Prometheus counters for AI enabled/disabled states; surface toggles in `/health` (~1 day).【F:app/services/ai_proof_flags.py†L6-L31】 |
| R6 | OCR provider transparency | Stub returns `{}` without metadata, so reviewers cannot distinguish provider errors from absent data. | Reviewer distrust & debugging friction | Medium | P1 | Record `ocr_status_reason`/error codes in metadata and implement a deterministic staging provider response (~1 day).【F:app/services/invoice_ocr.py†L93-L126】 |
| R7 | Metadata masking coverage | Blacklist masking can miss new metadata keys, potentially leaking sensitive supplier data or IBANs to AI or clients. | PII leakage | Low | P1 | Move to allowlist schemas per proof type and add unit tests asserting all metadata keys pass through masking helpers (~2 days).【F:app/utils/masking.py†L8-L110】 |

## I. AI Proof Advisor, OCR & risk scoring (dedicated section)
### I.1 AI architecture
- Settings default AI and OCR flags to `False`, list provider/model/timeouts, and are documented in `.env.example`, making the stack opt-in by environment variables.【F:app/config.py†L53-L67】【F:.env.example†L10-L25】
- `ai_proof_flags` is the single accessor for `ai_enabled`, provider, model, and timeout but simply returns cached settings, so it does not detect mid-flight config flips or emit telemetry.【F:app/services/ai_proof_flags.py†L6-L31】
- `ai_proof_advisor` builds a strict JSON-only prompt, masks sensitive metadata (`mask_proof_metadata`), and returns deterministic fallback payloads when API keys or SDKs are missing, ensuring AI outages degrade gracefully.【F:app/services/ai_proof_advisor.py†L27-L205】【F:app/utils/masking.py†L8-L110】

### I.2 AI integration into proof flows
- **Photo proofs**: After EXIF/geofence checks, AI is invoked only when `ai_enabled()` is true, and any exception is logged but ignored so proofs proceed. Auto-approved proofs immediately trigger payouts once AI metadata is stored.【F:app/services/proofs.py†L79-L335】
- **Document proofs**: OCR enrichment runs first, backend checks compute amount/IBAN/date/supplier diffs, and AI context includes these deterministic signals; document proofs never auto-approve, so AI remains advisory. Metadata sanitization strips client-supplied `ai_assessment` fields before persistence.【F:app/services/proofs.py†L67-L235】
- **Persistence & exposure**: AI outputs populate both metadata (`ai_assessment`) and DB columns (`ai_risk_level`, etc.), and schema responses expose them read-only. Reviewer decisions stamp `ai_reviewed_by/at` for governance.【F:app/services/proofs.py†L274-L399】【F:app/schemas/proof.py†L16-L44】
- **Guarantees**: AI can be disabled via settings, failures are caught locally, and contexts mask IBANs/URLs before sending to OpenAI, limiting data sharing to necessary fields.【F:app/services/ai_proof_advisor.py†L207-L343】【F:app/utils/masking.py†L8-L110】

### I.3 OCR & backend_checks
- `enrich_metadata_with_invoice_ocr` copies metadata, records `ocr_status`/provider, fills empty keys only, and logs (without raising) when providers fail, so proofs continue without OCR data.【F:app/services/invoice_ocr.py†L93-L126】
- `_normalize_invoice_ocr` standardizes amount/currency/date/supplier/IBAN last4 plus masked IBAN; only last4 or masked IBAN reach downstream consumers, aligning with privacy expectations.【F:app/services/invoice_ocr.py†L38-L90】
- `compute_document_backend_checks` compares expected vs invoice amounts, IBAN last4, date windows, and supplier names, returning structured dicts that feed AI context and reviewer UIs.【F:app/services/document_checks.py†L24-L155】

### I.4 AI/OCR-specific risks
| ID | Domain (AI/OCR) | Risk | Impact | Likelihood | Priority | Recommended fix |
| --- | --- | --- | --- | --- | --- | --- |
| AI-1 | AI toggle governance | Cached settings prevent runtime disablement across pods; incidents could leave some replicas still calling AI. | Inconsistent AI policy | Medium | P0 | Introduce per-request settings reload/TTL caching with Prometheus counters and `/health` exposure (ties to R5).【F:app/services/ai_proof_flags.py†L6-L31】 |
| AI-2 | OCR amount precision | Float conversions can round invoice totals, feeding inaccurate backend checks and AI context. | Monetary misclassification | High | P0 | Switch to Decimal math in OCR normalization/backend checks and add precision tests (ties to R1).【F:app/services/invoice_ocr.py†L38-L90】【F:app/services/document_checks.py†L43-L76】 |
| AI-3 | Masking breadth | Blacklist masking might miss new metadata keys, leaking PII to AI provider responses. | Privacy breach | Medium | P1 | Adopt allowlist serializers and unit tests covering new metadata fields (ties to R7).【F:app/utils/masking.py†L8-L110】 |

### I.5 Tests to add
- Decimal-preserving OCR test ensuring backend amount diffs remain exact even with high-precision strings once Decimal handling ships.
- Regression test verifying `/proofs` strips any `ai_assessment` key from client metadata so attackers cannot forge AI verdicts.
- Telemetry test simulating runtime toggle changes (e.g., monkeypatched settings reload) to confirm AI enable/disable flags propagate without restart.
- Fallback test that forces OpenAI SDK import failure to ensure proof submissions still succeed while logging degraded AI mode.

## J. Roadmap to a staging-ready MVP
- **P0 checklist**
  1. Implement Decimal-based OCR normalization and backend comparisons, add tests covering high-precision totals (R1/AI-2).
  2. Add dynamic secret/toggle reloads (e.g., TTL cache or DB table) plus `/health` fingerprints so PSP and AI policies can rotate live (R2/R5/AI-1).
  3. Emit audit logs for user/profile/payment reads and ensure reviewers see access trails (R3).
  4. Extend scheduler lock with TTL/owner metadata and expose status via `/health` to avoid stuck mandate jobs (R4).
  5. Instrument AI/OCR fallback metrics and log rate-limited warnings so operators see when advisory systems are disabled (R5/AI-1).

- **P1 checklist**
  - Improve OCR provider transparency by surfacing error reasons/status codes and wiring a deterministic staging provider (R6).
  - Replace blacklist metadata masking with schema-driven allowlists and add regression tests (R7/AI-3).
  - Enhance `/health` with DB connectivity and Alembic head checks to catch drift earlier.

- **P2 checklist**
  - Add admin endpoints for rotating PSP secrets and toggling AI/OCR with audit trails and Prometheus counters.
  - Publish reviewer dashboards summarizing backend checks, OCR status, and AI verdicts for analytics/export tooling.
  - Add correlation IDs/request logging to trace cross-service flows.

**Verdict: NO-GO for a staging with 10 real users** until Decimal-safe OCR math, runtime secret/toggle rotation, complete audit logging, resilient scheduler locking, and AI telemetry land.

## K. Verification evidence
- **Alembic review (conceptual)**: Reading `alembic/versions/013024e16da9_add_ai_fields_to_proofs.py`, `1b7cc2cfcc6e_add_ai_review_fields_to_proofs.py`, and `9c697d41f421_add_proof_requirements_to_milestones.py` confirms the latest heads contain AI/OCR schema; running `alembic current`, `alembic heads`, or `alembic history --verbose` in CI would verify the live DB matches these files (commands not executed during this static audit).【F:alembic/versions/013024e16da9_add_ai_fields_to_proofs.py†L1-L47】【F:alembic/versions/1b7cc2cfcc6e_add_ai_review_fields_to_proofs.py†L1-L31】【F:alembic/versions/9c697d41f421_add_proof_requirements_to_milestones.py†L1-L27】
- **`pytest -q` (not run)**: Coverage inferred from `tests/` includes AI flags/config (`tests/test_ai_config.py`), privacy masking (`tests/test_ai_privacy.py`), OCR enrichment (`tests/test_invoice_ocr.py`), AI review governance (`tests/test_proof_ai_review.py`), PSP webhooks (`tests/test_psp_webhook.py`), spend idempotency (`tests/test_spend_idempotency.py`), scheduler locks (`tests/test_scheduler_lock.py`), escrow/payments/mandates, and BO RBAC (various files).【F:tests/test_ai_config.py†L1-L24】【F:tests/test_ai_privacy.py†L10-L92】【F:tests/test_invoice_ocr.py†L1-L41】【F:tests/test_proof_ai_review.py†L11-L100】【F:tests/test_psp_webhook.py†L1-L169】【F:tests/test_spend_idempotency.py†L1-L88】【F:tests/test_scheduler_lock.py†L1-L11】
- **Key source anchors**: Security deps (`app/security.py†L19-L123`), lifespan setup (`app/main.py†L26-L138`), proof service (`app/services/proofs.py†L51-L350`), AI advisor (`app/services/ai_proof_advisor.py†L228-L343`), OCR/document checks (`app/services/invoice_ocr.py†L16-L126`, `app/services/document_checks.py†L24-L155`), PSP webhooks (`app/routers/psp.py†L19-L60`, `app/services/psp_webhooks.py†L57-L188`), and models (`app/models/*.py`) ground every finding.
