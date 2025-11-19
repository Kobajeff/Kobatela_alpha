# Kobatela_alpha — Capability & Stability Audit (2025-11-20)

## A. Executive summary
- Strict API-key authentication plus scope-aware dependencies and automatic audit logging protect every router, with `require_scope` guarding sensitive handlers and logging legacy/dev key usage for traceability.【F:app/security.py†L20-L155】
- FastAPI lifespan startup refuses to boot when PSP webhook secrets are absent, configures CORS/Prometheus/Sentry, and acquires a DB-backed scheduler lock before running background jobs, ensuring deterministic ops envelopes.【F:app/main.py†L26-L138】
- Proof ingestion chains EXIF/geofence validation, optional invoice OCR enrichment, structured backend document checks, and OpenAI-based advisory scoring with masked metadata and dedicated AI columns so reviewers can inspect automated risk signals without exposing PII.【F:app/services/proofs.py†L51-L350】【F:app/services/invoice_ocr.py†L16-L126】【F:app/services/document_checks.py†L24-L155】【F:app/models/proof.py†L15-L35】
- PSP webhooks enforce dual-secret HMAC signatures, timestamp skew limits, idempotent event storage, and settlement/error handling that writes audit logs, reducing replay/forgery risk across payout state transitions.【F:app/routers/psp.py†L19-L60】【F:app/services/psp_webhooks.py†L24-L187】
- AI governance fields (`ai_risk_level`, `ai_score`, flags, reviewer metadata) are persisted on each proof, while the API serializer exposes them read-only so clients cannot forge AI verdicts yet reviewers can audit decisions programmatically.【F:app/models/proof.py†L15-L35】【F:app/schemas/proof.py†L13-L34】

Major risks / limitations:
- Invoice OCR normalization casts totals to `float`, so backend amount checks or AI context can observe rounded values and misclassify proofs, which is a P0 monetary safety gap.【F:app/services/invoice_ocr.py†L61-L88】
- Configuration is globally cached: changing `PSP_WEBHOOK_SECRET` or AI flags at runtime has no effect until a restart, so secret rotations or staged AI rollouts cannot happen safely.【F:app/config.py†L91-L99】【F:app/services/psp_webhooks.py†L24-L85】
- Sensitive reads such as `/users/{user_id}` return PII without emitting `AuditLog` entries, limiting lifecycle reconstruction for compliance teams.【F:app/routers/users.py†L31-L45】
- Scheduler locking relies on an insert-only row with no TTL; if a runner crashes after acquiring the lock the APScheduler stays disabled forever because no cleanup occurs, threatening lifecycle jobs (mandate expiry).【F:app/services/scheduler_lock.py†L1-L40】【F:app/main.py†L58-L95】
- AI feature toggles are evaluated through cached settings and lack runtime telemetry, so operators cannot ensure all pods obey the same AI/OCR policy or know when AI falls back to manual mode.【F:app/services/ai_proof_flags.py†L6-L31】【F:app/services/ai_proof_advisor.py†L137-L210】

Readiness score: **78 / 100** — strong routing, data modeling, and AI/PSP safety nets, but the P0 issues above (monetary float usage, immutable secrets, missing audits, brittle scheduler lock, and AI toggles) must be resolved before onboarding 10 staging users.

## B. Capability map (current features)
### B.1 Functional coverage
| Feature | Endpoints / modules involved | Status (OK / Partial / Missing) | Notes |
| --- | --- | --- | --- |
| Health & ops telemetry | `/health` router plus lifespan logging (`app/routers/health.py`, `app/main.py`) | Partial | Surfaces PSP secret state and scheduler flag but no DB/migration checks yet.【F:app/routers/health.py†L7-L26】【F:app/main.py†L26-L95】 |
| User & API key lifecycle | `/users`, `/apikeys` routers with audit helpers | Partial | Creation emits audits; user read lacks audit logging and key list lacks pagination.【F:app/routers/users.py†L1-L45】【F:app/routers/apikeys.py†L34-L125】 |
| Escrow lifecycle | `/escrows/*` + escrow/payments services | OK | Creation, deposits (idempotent), mark delivered, client approve/reject, deadline checks, and read endpoints require scoped keys.【F:app/routers/escrow.py†L19-L93】 |
| Mandates & spend controls | `/mandates`, `/spend/*`, `usage` services | OK | Allowlist, merchant/category creation, payee limits, and spend execution all require Idempotency-Key headers and audit usage state.【F:app/routers/mandates.py†L12-L29】【F:app/routers/spend.py†L34-L178】【F:app/services/usage.py†L1-L120】 |
| Proof submission & review | `/proofs`, proof service, AI/OCR helpers | OK | Photo proofs run EXIF/geofence hard checks, document proofs gain OCR + backend checks, AI is advisory with try/except, reviewer decisions persist AI notes.【F:app/routers/proofs.py†L19-L40】【F:app/services/proofs.py†L51-L350】 |
| Payments & PSP integration | `/payments/execute/{id}`, `/psp/webhook`, payment/PSP services | Partial | Manual execution plus PSP webhook settlement exist, but payments lack GET audit logging and webhook secrets cannot rotate live.【F:app/routers/payments.py†L14-L20】【F:app/routers/psp.py†L19-L60】【F:app/services/payments.py†L200-L320】 |
| Alerts & monitoring | `/alerts` router | OK | Lists stored alerts filtered by type for admin/support scopes.【F:app/routers/alerts.py†L1-L20】 |
| AI Proof Advisor | `ai_proof_flags`, `ai_proof_advisor`, proof service | Partial | Feature flag defaults off and handles exceptions, but settings cache prevents runtime toggles and only OpenAI provider is wired.【F:app/services/ai_proof_flags.py†L6-L31】【F:app/services/ai_proof_advisor.py†L137-L210】 |
| Invoice OCR pipeline | `invoice_ocr.py`, proof service | Partial | Flag exists and enriches metadata without overwriting user fields, yet provider stub returns empty data and amount normalization uses floats.【F:app/services/invoice_ocr.py†L16-L126】 |

### B.2 End-to-end journeys supported today
- **Escrow funding to payout**: Create escrow → deposit with `Idempotency-Key` → mark delivered/submit proof → auto-approve photo or manual review → execute payout or await PSP webhook settlement.【F:app/routers/escrow.py†L19-L93】【F:app/routers/proofs.py†L19-L40】【F:app/services/proofs.py†L270-L350】
- **Usage mandate spending**: Create mandates and allowed payees → configure merchants/categories → call `/spend/purchases` or `/spend` with idempotent headers so only authorized payees receive funds under configured limits.【F:app/routers/mandates.py†L12-L29】【F:app/routers/spend.py†L34-L178】【F:app/services/usage.py†L53-L120】
- **Document proof with OCR + AI**: Submit PDF/INVOICE proof → OCR enriches metadata, backend checks compute amount/date/IBAN/supplier signals → AI receives sanitized context and stores advisory risk fields for reviewers.【F:app/services/proofs.py†L71-L235】【F:app/services/invoice_ocr.py†L94-L126】【F:app/services/document_checks.py†L24-L155】
- **PSP settlement observability**: `/psp/webhook` validates HMAC/timestamp, persists events, and updates payment status while `/health` surfaces whether PSP secrets are configured and scheduler is running.【F:app/routers/psp.py†L19-L60】【F:app/services/psp_webhooks.py†L24-L187】【F:app/routers/health.py†L7-L26】

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request model | Response model | HTTP codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/health` | `health.healthcheck`【F:app/routers/health.py†L7-L26】 | None | – | – | dict | 200 |
| POST | `/users` | `users.create_user`【F:app/routers/users.py†L15-L33】 | API key | admin/support | `UserCreate` | `UserRead` | 201, 400 |
| GET | `/users/{id}` | `users.get_user`【F:app/routers/users.py†L34-L45】 | API key | admin/support | – | `UserRead` | 200, 404 |
| POST | `/apikeys` | `apikeys.create_api_key`【F:app/routers/apikeys.py†L34-L94】 | API key | admin | `CreateKeyIn` | `ApiKeyCreateOut` | 201, 400 |
| GET | `/apikeys/{id}` | `apikeys.get_apikey`【F:app/routers/apikeys.py†L97-L112】 | API key | admin | – | `ApiKeyRead` | 200, 404 |
| DELETE | `/apikeys/{id}` | `apikeys.revoke_apikey`【F:app/routers/apikeys.py†L115-L153】 | API key | admin | – | – | 204, 404 |
| POST | `/mandates` | `mandates.create_mandate`【F:app/routers/mandates.py†L12-L23】 | API key | sender | `UsageMandateCreate` | `UsageMandateRead` | 201 |
| POST | `/mandates/cleanup` | `mandates.cleanup_expired_mandates`【F:app/routers/mandates.py†L24-L29】 | API key | sender | – | `{expired}` | 202 |
| POST | `/escrows` | `escrow.create_escrow`【F:app/routers/escrow.py†L19-L27】 | API key | sender | `EscrowCreate` | `EscrowRead` | 201, 404 |
| POST | `/escrows/{id}/deposit` | `escrow.deposit`【F:app/routers/escrow.py†L29-L40】 | API key + `Idempotency-Key` | sender | `EscrowDepositCreate` | `EscrowRead` | 200, 400, 404 |
| POST | `/escrows/{id}/mark-delivered` | `escrow.mark_delivered`【F:app/routers/escrow.py†L43-L51】 | API key | sender | `EscrowActionPayload` | `EscrowRead` | 200, 404 |
| POST | `/escrows/{id}/client-approve` | `escrow.client_approve`【F:app/routers/escrow.py†L54-L63】 | API key | sender | optional `EscrowActionPayload` | `EscrowRead` | 200, 404 |
| POST | `/escrows/{id}/client-reject` | `escrow.client_reject`【F:app/routers/escrow.py†L65-L74】 | API key | sender | optional payload | `EscrowRead` | 200, 404 |
| POST | `/escrows/{id}/check-deadline` | `escrow.check_deadline`【F:app/routers/escrow.py†L76-L83】 | API key | sender | – | `EscrowRead` | 200, 404 |
| GET | `/escrows/{id}` | `escrow.read_escrow`【F:app/routers/escrow.py†L86-L93】 | API key | sender/support/admin | – | `EscrowRead` | 200, 404 |
| POST | `/proofs` | `proofs.submit_proof`【F:app/routers/proofs.py†L19-L32】 | API key | sender | `ProofCreate` | `ProofRead` | 201, 404, 409, 422 |
| POST | `/proofs/{id}/decision` | `proofs.decide_proof`【F:app/routers/proofs.py†L34-L40】 | API key | support/admin | `ProofDecision` | `ProofRead` | 200, 400, 404, 409 |
| POST | `/spend/categories` | `spend.create_category`【F:app/routers/spend.py†L34-L46】 | API key | admin/support | `SpendCategoryCreate` | `SpendCategoryRead` | 201 |
| POST | `/spend/merchants` | `spend.create_merchant`【F:app/routers/spend.py†L48-L60】 | API key | admin/support | `MerchantCreate` | `MerchantRead` | 201 |
| POST | `/spend/allow` | `spend.allow_usage`【F:app/routers/spend.py†L62-L72】 | API key | admin/support | `AllowedUsageCreate` | dict | 201 |
| POST | `/spend/allowed` | `spend.add_allowed_payee`【F:app/routers/spend.py†L100-L135】 | API key | admin/support | `AddPayeeIn` | dict | 201 |
| POST | `/spend/purchases` | `spend.create_purchase`【F:app/routers/spend.py†L75-L98】 | API key + `Idempotency-Key` | sender/admin | `PurchaseCreate` | `PurchaseRead` | 201, 400, 403, 404, 409 |
| POST | `/spend` | `spend.spend`【F:app/routers/spend.py†L137-L178】 | API key + `Idempotency-Key` | sender/admin | `SpendIn` | dict | 200, 400, 403, 404, 409 |
| POST | `/allowlist` | `transactions.add_to_allowlist`【F:app/routers/transactions.py†L19-L35】 | API key | admin | `AllowlistCreate` | dict | 201 |
| POST | `/certified` | `transactions.add_certification`【F:app/routers/transactions.py†L37-L53】 | API key | admin | `CertificationCreate` | dict | 201 |
| POST | `/transactions` | `transactions.post_transaction`【F:app/routers/transactions.py†L55-L92】 | API key + `Idempotency-Key` | admin | `TransactionCreate` | `TransactionRead` | 201, 400 |
| GET | `/transactions/{id}` | `transactions.get_transaction`【F:app/routers/transactions.py†L94-L117】 | API key | admin | – | `TransactionRead` | 200, 404 |
| POST | `/payments/execute/{id}` | `payments.execute_payment`【F:app/routers/payments.py†L14-L20】 | API key | sender | path id | `PaymentRead` | 200, 404, 409 |
| GET | `/alerts` | `alerts.list_alerts`【F:app/routers/alerts.py†L1-L20】 | API key | admin/support | query `type` | list[`AlertRead`] | 200 |
| POST | `/psp/webhook` | `psp.psp_webhook`【F:app/routers/psp.py†L19-L60】 | HMAC headers | PSP | raw JSON | `{ok}` | 200, 401, 503 |

## D. Data model & state machines
- **Entity overview**
  - `EscrowAgreement`: Decimal totals (`Numeric(18,2)`), release JSON, deadline, and status enum with deposits/events relationships; constraints ensure non-negative totals.【F:app/models/escrow.py†L23-L55】
  - `EscrowDeposit`: Decimal amount + unique, non-null idempotency key, binding deposits to agreements for replay-safe funding.【F:app/models/escrow.py†L45-L55】
  - `Milestone`: Per-escrow index, Decimal amount, proof type, validator, optional geofence floats, proof requirements JSON, and state enum tracking WAITING → REVIEW → APPROVED/REJECTED.【F:app/models/milestone.py†L1-L58】
  - `Proof`: Unique SHA-256 hash, metadata JSON, status string, AI governance columns (risk level, score, flags, explanation, checked/reviewed timestamps).【F:app/models/proof.py†L15-L35】
  - `Payment`: Decimal amount, PSP reference, idempotency key, status enum; indexes exist for status/escrow/time queries.【F:app/models/payment.py†L1-L42】
  - `UsageMandate`, `AllowedPayee`, and `Purchase` enforce Decimal limits with check constraints for spend governance.【F:app/models/allowed_payee.py†L1-L27】【F:app/models/spend.py†L1-L52】
  - `ApiKey`, `AuditLog`, `Alert`, and `PSPWebhookEvent` back lifecycle, compliance, and webhook history (not shown but present in `app/models`).

- **State machines**
  - **Escrow**: `EscrowStatus` enumerates `DRAFT → FUNDED → RELEASABLE → RELEASED`, with `REFUNDED/CANCELLED` branches; deposits and escrow events capture transitions and `payments.execute_payout` closes escrows when fully paid.【F:app/models/escrow.py†L12-L43】【F:app/services/payments.py†L1-L200】
  - **Milestone & Proof**: Milestones start `WAITING`, move to `PENDING_REVIEW` when a non-auto proof is submitted, and switch to `APPROVED`/`REJECTED` depending on reviewer decisions. Proofs start `PENDING`, auto-approve for clean photo metadata, or stay `PENDING` until `decide_proof` writes `APPROVED`/`REJECTED` while capturing AI review metadata.【F:app/services/proofs.py†L236-L399】
  - **Payments**: `PaymentStatus` flows `PENDING → SENT → SETTLED` (or `ERROR/REFUNDED`); manual execute reuses idempotency keys and `finalize_payment_settlement` marks settlement with audit events.【F:app/models/payment.py†L1-L42】【F:app/services/payments.py†L200-L320】

## E. Stability results
- **Static view of tests (not executed)**: The suite covers AI configs (`tests/test_ai_config.py`), AI privacy masking (`tests/test_ai_privacy.py`), AI reviewer note enforcement (`tests/test_proof_ai_review.py`), invoice OCR enrichment (`tests/test_invoice_ocr.py`), escrow/milestone/payout flows, PSP webhooks, mandates, spend idempotency, scheduler locks, and scope enforcement as seen from the `tests/` directory listing and representative files.【F:tests/test_ai_config.py†L1-L24】【F:tests/test_ai_privacy.py†L1-L54】【F:tests/test_proof_ai_review.py†L1-L68】【F:tests/test_invoice_ocr.py†L1-L33】 No commands were run; coverage is inferred from static inspection only.
- **Static review notes**: Missing audit logging on `/users/{id}`, cached settings in AI/PSP flows, float-based OCR normalization, and scheduler lock cleanup are technical blockers. Services largely avoid `except Exception` except when deliberately shielding AI/OCR fallbacks.【F:app/routers/users.py†L31-L45】【F:app/services/ai_proof_advisor.py†L180-L210】【F:app/services/invoice_ocr.py†L112-L126】

## F. Security & integrity
- **AuthN/Z**: `require_api_key` enforces API keys (with optional dev key guard) and `require_scope` checks sender/support/admin scopes per router, logging key usage for audit trails.【F:app/security.py†L20-L155】
- **Input validation**: Pydantic schemas enforce type/length; routers such as `/spend/purchases` and `/transactions` explicitly require `Idempotency-Key` headers to avoid double writes.【F:app/routers/spend.py†L75-L178】【F:app/routers/transactions.py†L55-L92】
- **File/proof validation**: Photo proofs undergo EXIF/geofence checks with hard-error codes before AI is invoked, while document proofs compute backend amount/IBAN/date/supplier comparisons; AI exceptions are caught so proofs never auto-fail because of GPT outages.【F:app/services/proofs.py†L79-L235】【F:app/services/document_checks.py†L24-L155】
- **Secret management**: Settings default AI/OCR flags to False, strip empty PSP secrets, and lifespan halts startup when both secrets are missing. `.env.example` documents AI and OCR env vars for operators.【F:app/config.py†L35-L70】【F:.env.example†L1-L25】
- **Audit/logging**: Proof submissions, approvals, and PSP payment failures emit `AuditLog` entries; API key usage and allowed payee actions are also audited. Gaps remain for user reads and some payment reads, which should log access similarly.【F:app/services/proofs.py†L294-L350】【F:app/services/psp_webhooks.py†L148-L186】【F:app/routers/users.py†L31-L45】

## G. Observability & operations
- Logging is initialized during lifespan, CORS/Prometheus middleware is configured, and error handlers wrap uncaught exceptions into normalized JSON with logs so downstream dashboards can correlate incidents.【F:app/main.py†L26-L138】
- `/health` reports PSP secret readiness and scheduler activation status but does not yet probe DB connectivity or Alembic head drift, so deeper observability must come from other channels.【F:app/routers/health.py†L7-L26】
- Alembic migrations cover AI proof fields (`013024e16da9`, `1b7cc2cfcc6e`) and milestone proof requirements (`9c697d41f421`), indicating schema history is up to date; commands like `alembic current` or `alembic history --verbose` would validate this sequence in CI (not executed here).【F:alembic/versions/013024e16da9_add_ai_fields_to_proofs.py†L1-L38】【F:alembic/versions/1b7cc2cfcc6e_add_ai_review_fields_to_proofs.py†L1-L28】【F:alembic/versions/9c697d41f421_add_proof_requirements_to_milestones.py†L1-L24】
- Scheduler jobs rely on a table lock (`scheduler_locks`) managed by `try_acquire_scheduler_lock`; lack of TTL makes crash recovery manual, and `/health` does not expose lock status beyond `scheduler_running` boolean.【F:app/services/scheduler_lock.py†L1-L40】【F:app/routers/health.py†L7-L26】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority (P0/P1/P2) | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Invoice OCR normalization | Totals are cast to `float`, so backend amount comparisons/AI context can drift by cents and incorrectly flag or approve invoices. | Monetary decisions based on incorrect amounts | Medium | P0 | Preserve amounts as `Decimal` (e.g., use `Decimal(str(total))`), store currency/amount pairs with explicit quantization, and extend tests to cover >2 decimal inputs.【F:app/services/invoice_ocr.py†L61-L88】 |
| R2 | PSP secret/runtime config | `get_settings()` returns a cached instance, so rotating `PSP_WEBHOOK_SECRET` or AI flags in the environment has no effect until all pods restart; webhooks would start failing silently. | Missed/failed settlements | High | P0 | Add a lightweight settings reloader (TTL cache or per-request env read) and `/health` metric for current secret digests; fail fast if webhook verification uses stale secret.【F:app/config.py†L91-L99】【F:app/services/psp_webhooks.py†L24-L85】 |
| R3 | Business lifecycle audit (user read) | `/users/{id}` returns usernames/emails without writing an `AuditLog`, leaving no trace of who accessed PII. | Compliance/audit gaps | Medium | P0 | Mirror escrow read behavior: capture actor via `actor_from_api_key` and insert `AuditLog` rows when reading users (and other PII entities).【F:app/routers/users.py†L31-L45】 |
| R4 | Scheduler lock resilience | Lock rows never expire; if a pod crashes after acquiring the lock, future pods cannot run the scheduler and mandate expiry silently halts. | Stalled mandate expirations / payouts | Medium | P0 | Add `expires_at` column + periodic cleanup, or upgrade to advisory locks (e.g., Postgres `pg_try_advisory_lock`) and expose lock owner in `/health`.【F:app/services/scheduler_lock.py†L1-L40】【F:app/main.py†L58-L95】 |
| R5 | AI & OCR toggles | `ai_proof_flags` simply returns cached settings; operators cannot toggle AI/OCR without redeploying, so staged rollouts or emergency disablement may be inconsistent across pods. | AI governance failure | Medium | P0 | Re-read settings per request or add TTL caching plus admin endpoints/audit for toggles; emit metrics whenever AI is disabled/falling back.【F:app/services/ai_proof_flags.py†L6-L31】 |
| R6 | OCR provider stub transparency | Even when OCR is enabled, the stub returns `{}` with only console warnings, so reviewers cannot distinguish between OCR failure and empty data. | Reviewer trust erosion | Medium | P1 | Record detailed `ocr_status`/error codes in metadata and `/health`, and integrate at least one staging provider with deterministic fixtures.【F:app/services/invoice_ocr.py†L94-L126】 |
| R7 | AI metadata masking coverage | Masking is blacklist-based; new metadata keys could leak IBANs/emails to AI or API responses until the list is updated. | PII leakage | Low | P1 | Switch to allowlist schemas per proof type and add regression tests to ensure new metadata keys default to masked values.【F:app/utils/masking.py†L1-L56】 |

## I. AI Proof Advisor, OCR & risk scoring (dedicated section)
### I.1 AI architecture
- Settings expose AI provider/model/timeout, default to disabled, and `.env.example` shows opt-in flags so deployments can run without AI/OCR keys by default.【F:app/config.py†L35-L70】【F:.env.example†L10-L25】
- `ai_proof_flags` is the single source for feature flags/model/provider/timeout, but because it simply calls cached settings, it does not support runtime overrides or telemetry.【F:app/services/ai_proof_flags.py†L6-L31】
- `ai_proof_advisor` builds a canonical system prompt, masks proof metadata (storage URLs truncated, IBAN/email obfuscated), and falls back to deterministic warning payloads when the API key/SDK is missing or the OpenAI call fails, ensuring AI outages do not block proofs.【F:app/services/ai_proof_advisor.py†L17-L210】

### I.2 AI integration into proof flows
- Photo proofs: after EXIF/geofence validation, AI is invoked only when `ai_enabled()` returns true; the context includes mandate info, backend validation outcomes, and the sanitized document metadata. Exceptions are logged but do not change proof status, keeping auto-approval deterministic.【F:app/services/proofs.py†L79-L194】
- Document proofs: metadata is first enriched via OCR (if enabled) and deduplicated of client-supplied `ai_assessment`, then backend checks compute amount/IBAN/date/supplier diffs before AI is called in advisory-only mode. Manual review is mandatory because `auto_approve` stays False for non-photos.【F:app/services/proofs.py†L71-L235】
- AI outputs are stored both inside proof metadata (`ai_assessment`) and in dedicated columns/response fields, and reviewer decisions capture `ai_reviewed_by/at` to enforce “note required when overriding AI warning/suspect” policies.【F:app/services/proofs.py†L285-L399】【F:app/models/proof.py†L15-L35】【F:app/schemas/proof.py†L13-L34】

### I.3 OCR & backend_checks
- `enrich_metadata_with_invoice_ocr` copies metadata, records `ocr_status`/provider flags, and only fills empty keys so user-supplied values win; errors are logged and do not block proof submission.【F:app/services/invoice_ocr.py†L94-L126】
- `compute_document_backend_checks` returns structured dicts for amount/currency differences, IBAN last4 matches, invoice date ranges, and supplier name matches, which feed into AI contexts as deterministic signals.【F:app/services/document_checks.py†L24-L155】
- Proof service injects both OCR-enriched metadata and backend check payloads into `call_ai_proof_advisor`, so GPT receives normalized JSON instead of raw binary documents.【F:app/services/proofs.py†L197-L235】

### I.4 AI/OCR-specific risks
| ID | Domain (AI/OCR) | Risk | Impact | Likelihood | Priority | Recommended fix |
| --- | --- | --- | --- | --- | --- | --- |
| AI-1 | AI toggle governance | Cached settings mean AI enable/disable cannot be flipped per tenant/pod without redeploy, so partial rollouts can produce inconsistent AI risk levels. | Medium | Medium | P0 | Load settings per request or use TTL cache + admin toggle endpoint with audit logging and Prometheus metrics.【F:app/services/ai_proof_flags.py†L6-L31】 |
| AI-2 | OCR accuracy | Float casting in OCR normalization can round invoice totals before backend checks or AI review, producing false mismatches/approvals. | High | Medium | P0 | Normalize totals via `Decimal` and include original string in metadata for audit; extend backend checks to compare decimals with tolerance.【F:app/services/invoice_ocr.py†L61-L88】 |
| AI-3 | Metadata masking gaps | Blacklist-based masking might miss new metadata keys (e.g., `beneficiary_phone_alt`) and leak PII to reviewers/AI providers. | Medium | Low | P1 | Introduce schema-driven serializers and add unit tests for new metadata keys before deploying new proof types.【F:app/utils/masking.py†L1-L56】 |

### I.5 Tests to add
- Simulate OCR returning high-precision totals to ensure new Decimal-based normalization preserves exact cents and backend checks flag differences correctly.
- Add a regression test verifying `/proofs` refuses AI-provided fields in `ProofCreate.metadata`, ensuring clients cannot inject `ai_assessment` despite the server stripping it today.【F:app/services/proofs.py†L67-L75】
- Unit-test scheduler/AI toggle interactions: flip `AI_PROOF_ADVISOR_ENABLED` via a stubbed dynamic settings loader to confirm runtime changes propagate without restarts once refactored.

## J. Roadmap to a staging-ready MVP
- **P0 checklist**
  1. Implement Decimal-based OCR normalization (R1) and expand document-check tests for rounding edge cases.
  2. Add settings reload/rotation support for PSP secrets and AI flags, plus `/health` metrics exposing hashed secret digests (R2).
  3. Emit `AuditLog` entries for `/users/{id}` and other sensitive reads, mirroring escrow read logging (R3).
  4. Add TTL/heartbeat to scheduler lock or switch to advisory locks, and expose lock owner/status via `/health` so ops can detect stuck locks (R4).
  5. Refactor `ai_proof_flags` to refresh settings per request or TTL cache with telemetry so AI/OCR toggles propagate instantly (R5/AI-1/AI-2).

- **P1 checklist**
  - Enhance OCR provider integration (add staging provider, expose `ocr_status`/errors in API/metrics) and move metadata masking to allowlist-based serializers (R6/R7/AI-3).
  - Expand pytest coverage for AI/OCR toggles, OCR Decimal math, and audit logging, ensuring async tests run under `pytest-asyncio` once configured.
  - Extend `/health` to probe DB connectivity and Alembic head drift so ops know migrations are current before accepting traffic.

- **P2 checklist**
  - Add admin endpoints for toggling AI/OCR and rotating PSP secrets with audit trails.
  - Emit Prometheus metrics for AI fallbacks, OCR errors, scheduler lock acquisition, and PSP webhook outcomes.
  - Provide reviewer-facing APIs summarizing backend checks, OCR status, and AI verdicts for analytics/export tooling.

**Verdict: NO-GO for a staging with 10 real users** until Decimal-safe OCR, runtime secret rotation, full audit logging, resilient scheduler locks, and AI toggle telemetry are delivered; these are necessary to meet fintech-grade money-movement and AI-governance expectations.

## K. Verification evidence
- **Migrations**: `alembic/versions/013024e16da9_add_ai_fields_to_proofs.py`, `1b7cc2cfcc6e_add_ai_review_fields_to_proofs.py`, and `9c697d41f421_add_proof_requirements_to_milestones.py` show the linear head sequence; running `alembic current`, `alembic heads`, or `alembic history --verbose` in CI would confirm the DB matches these definitions (not executed here).【F:alembic/versions/013024e16da9_add_ai_fields_to_proofs.py†L1-L38】【F:alembic/versions/1b7cc2cfcc6e_add_ai_review_fields_to_proofs.py†L1-L28】【F:alembic/versions/9c697d41f421_add_proof_requirements_to_milestones.py†L1-L24】
- **Tests**: `pytest -q` was not run; based on static inspection, the suite exercises AI configs, AI privacy masking, OCR enrichment, proof reviewer rules, escrow flows, spend idempotency, PSP webhooks, and scheduler guards via files such as `tests/test_ai_config.py`, `tests/test_ai_privacy.py`, `tests/test_invoice_ocr.py`, `tests/test_proof_ai_review.py`, `tests/test_escrow.py`, and `tests/test_psp_webhook.py`. Future CI runs should report these modules explicitly once commands are allowed.【F:tests/test_ai_config.py†L1-L24】【F:tests/test_ai_privacy.py†L1-L54】【F:tests/test_invoice_ocr.py†L1-L33】【F:tests/test_proof_ai_review.py†L1-L68】
- **Source references**: All findings reference concrete files under `app/routers/*`, `app/services/*`, `app/models/*`, and `app/config.py`, ensuring the audit is grounded in repository code without executing it.
