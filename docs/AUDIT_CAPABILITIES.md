# Kobatela_alpha — Capability & Stability Audit (2025-11-21)

## A. Executive summary
- API surface covers escrow lifecycle, proof submission/decision, PSP webhook handling, spend controls, and public-sector aggregation, all guarded by API-key scopes and audit logs on critical reads/writes. 【F:app/routers/escrow.py†L21-L107】【F:app/routers/proofs.py†L24-L54】【F:app/routers/psp.py†L17-L67】【F:app/routers/spend.py†L21-L116】【F:app/routers/kct_public.py†L21-L163】
- AI Proof Advisor and invoice OCR are feature-flagged off by default, with fallback paths, masking, and circuit-breaker behavior to prevent blocking flows when misconfigured. 【F:app/config.py†L54-L68】【F:app/services/ai_proof_advisor.py†L436-L470】【F:.env.example†L10-L25】
- Proof flow normalizes invoice amounts/currency, enriches metadata with OCR without overwriting user input, and persists AI assessments into dedicated columns plus audit logs. 【F:app/services/proofs.py†L83-L123】【F:app/services/invoice_ocr.py†L274-L305】【F:app/models/proof.py†L29-L49】
- Health endpoint surfaces DB/migration state, AI/OCR toggles, scheduler status, and PSP secret fingerprints for operational visibility. 【F:app/routers/health.py†L104-L142】
- Test suite statically covers AI flags/privacy/resilience, OCR normalization, EXIF/geofence/photo rules, PSP webhook signing, scheduler locks, spend idempotency, and health telemetry. 【F:tests/test_ai_config.py†L1-L44】【F:tests/test_ai_privacy.py†L1-L120】【F:tests/test_invoice_ocr.py†L1-L140】【F:tests/test_milestone_sequence_and_exif.py†L1-L160】【F:tests/test_psp_webhook.py†L1-L200】【F:tests/test_scheduler_lock.py†L1-L120】

Major risks / limitations:
- Geofence latitude/longitude/radius on milestones use Float, risking precision drift in distance checks and geofence decisions. 【F:app/models/milestone.py†L56-L59】【F:app/services/proofs.py†L137-L180】
- Invoice normalization raises hard 422 errors; OCR is invoked with empty bytes and could add latency without async offloading. 【F:app/services/proofs.py†L87-L120】【F:app/services/invoice_ocr.py†L179-L218】
- AI circuit breaker and stats are in-memory per process; missing API key or disabled flag increments error counters and returns fallback but still counts as error. 【F:app/services/ai_proof_advisor.py†L436-L507】
- Settings caching (60s) may delay PSP secret rotations or AI/OCR flag changes; PSP webhook drift window is fixed in config. 【F:app/config.py†L96-L116】【F:app/config.py†L35-L40】
- No executed tests/migrations in this audit (static analysis only); runtime stability unverified.

Readiness score (staging MVP): **78 / 100** — strong route coverage and controls, but monetary precision, AI/OCR resilience, and config refresh need tightening before external pilots.

## B. Capability map (current features)
### B.1 Functional coverage
| Feature | Endpoints / modules involved | Status (OK / Partial / Missing) | Notes |
| --- | --- | --- | --- |
| Health & runtime introspection | `/health` | OK | Returns DB/migration status, PSP secret fingerprints, AI/OCR flags, scheduler state, and KCT public feature flag. 【F:app/routers/health.py†L104-L142】 |
| User/API key management | `/users`, `/apikeys` | Partial | CRUD and audit hooks exist; pagination/search depth unclear. 【F:app/routers/users.py†L16-L98】【F:app/routers/apikeys.py†L37-L116】 |
| Escrow lifecycle | `/escrows/*` | OK | Create, deposit (idempotency key), delivery marking, client approve/reject, deadline check, and read with audit log. 【F:app/routers/escrow.py†L21-L107】 |
| Proof submission & decision | `/proofs` | OK | Photo EXIF/geofence validation, invoice OCR enrichment, AI advisory, auto-approval path, manual decisions with AI note guard. 【F:app/services/proofs.py†L67-L455】【F:app/routers/proofs.py†L24-L54】 |
| Payments & PSP webhook | `/payments/execute/{id}`, `/psp/webhook` | OK | Manual execution plus HMAC/timestamp verification and replay defense. 【F:app/routers/payments.py†L18-L63】【F:app/services/psp_webhooks.py†L100-L228】 |
| Spend controls & transactions | `/spend/*`, `/transactions` | OK | Allowlist, merchants, purchases with idempotency, admin transactions, and spend usage mandates. 【F:app/routers/spend.py†L21-L116】【F:app/routers/transactions.py†L21-L86】 |
| Alerts & public sector views | `/alerts`, `/kct_public/*` | OK | Alerts listing and GOV/ONG scoped public mandate aggregation. 【F:app/routers/alerts.py†L7-L40】【F:app/routers/kct_public.py†L21-L163】 |
| AI & OCR toggles | `ai_proof_flags`, `invoice_ocr` | Partial | Feature flags, masking, fallback paths; OCR provider is dummy only. 【F:app/services/ai_proof_flags.py†L10-L31】【F:app/services/invoice_ocr.py†L179-L218】 |
| Scheduler | Lifespan + lock | OK | Optional scheduler with DB lock heartbeat and health description. 【F:app/main.py†L64-L134】【F:app/services/scheduler_lock.py†L36-L116】 |

### B.2 End-to-end journeys supported today
- Photo proof: sender submits with EXIF/geofence validation → optional AI advisory → auto-approve if clean → payout with idempotent key and audit trail. 【F:app/services/proofs.py†L126-L455】
- Invoice/contract proof: sender submits → OCR enrichment and normalization → backend checks → AI advisory (manual review) → AI fields persisted with audit. 【F:app/services/proofs.py†L83-L380】【F:app/services/document_checks.py†L36-L170】
- PSP settlement: webhook verifies HMAC/timestamp and deduplicates event IDs before updating payment status. 【F:app/services/psp_webhooks.py†L100-L228】
- Spend/transaction controls: allowlists, merchants, purchases, and transactions with idempotency and scoped access. 【F:app/routers/spend.py†L21-L116】【F:app/routers/transactions.py†L21-L86】
- Scheduler safety: lock acquire/refresh/release during lifespan with health visibility. 【F:app/main.py†L64-L134】【F:app/services/scheduler_lock.py†L36-L116】

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
  - Proof: sha256-unique proofs with metadata JSON, invoice amount/currency (Numeric(18,2)), AI assessment fields (risk level/score/flags/explanation/checked_at/reviewer). 【F:app/models/proof.py†L16-L49】
  - Milestone: per-escrow unique idx, Numeric(18,2) amount, proof_requirements JSON, geofence lat/lng/radius as Float, status enum. 【F:app/models/milestone.py†L32-L62】
  - EscrowAgreement/Deposit/Event: statuses, deadlines, positive deposit amounts with idempotency keys (in service layer). 【F:app/models/escrow.py†L12-L55】【F:app/services/escrow.py†L19-L154】
  - Payment: Numeric amount, unique PSP reference/idempotency keys, status enum. 【F:app/models/payment.py†L16-L38】
  - API Key: scoped tokens with unique hash/prefix and audit on use. 【F:app/models/api_key.py†L11-L32】【F:app/security.py†L33-L133】
  - AuditLog: actor/action/entity/data_json/at fields. 【F:app/models/audit.py†L8-L17】
  - SchedulerLock: owner/expires_at with indexes for lock heartbeat. 【F:app/models/scheduler_lock.py†L11-L24】
- State machines:
  - Proof: WAITING milestone → submit sets proof PENDING or APPROVED (photo auto-approve) → decision approve/reject updates milestone and AI review markers; approvals trigger payout via payments_service. 【F:app/services/proofs.py†L126-L455】【F:app/services/proofs.py†L458-L513】
  - Escrow: statuses enumerated with deposit events and deadline checks driving release/refund flows. 【F:app/models/escrow.py†L12-L46】【F:app/services/escrow.py†L67-L154】
  - Payment: PENDING→SENT/SETTLED/ERROR/REFUNDED via manual execution or PSP webhook events. 【F:app/models/payment.py†L16-L30】【F:app/services/psp_webhooks.py†L174-L228】
  - Scheduler lock: acquire→refresh→release lifecycle to ensure single runner. 【F:app/services/scheduler_lock.py†L36-L116】

## E. Stability results
- Static view of tests (not executed): coverage includes AI flags/resilience/privacy, OCR normalization and contract variant, proof flows (EXIF/geofence, auto-approve, AI review notes, invoice normalization), PSP webhook signing/drift, scheduler lock, spend idempotency, scopes/auth, health telemetry, and table presence. 【F:tests/test_ai_resilience.py†L1-L140】【F:tests/test_ai_privacy.py†L1-L120】【F:tests/test_invoice_ocr_contract.py†L1-L160】【F:tests/test_milestone_sequence_and_exif.py†L1-L160】【F:tests/test_psp_webhook.py†L1-L200】【F:tests/test_spend_idempotency.py†L1-L140】【F:tests/test_health.py†L1-L120】【F:tests/test_tables.py†L1-L120】
- Skips/xfails: none evident from static inspection.
- Static review notes: synchronous AI/OCR in request path could slow responses; geofence math uses float; settings caching may hide config changes; AI circuit breaker and metrics are process-local; duplicate idempotency checks in some routers (transactions). 【F:app/services/proofs.py†L137-L200】【F:app/services/ai_proof_advisor.py†L436-L507】【F:app/config.py†L96-L116】【F:app/routers/transactions.py†L46-L68】

## F. Security & integrity
- AuthN/Z: API-key dependency with scopes (sender/support/admin); legacy dev key allowed only in dev; GOV/ONG guard for public routes; audits recorded on API key use. 【F:app/security.py†L11-L183】【F:app/routers/kct_public.py†L21-L163】
- Input validation: Pydantic schemas bound proof fields, decision normalization, spend/payee sizes, and OCR output validation via Pydantic model. 【F:app/schemas/proof.py†L5-L38】【F:app/services/invoice_ocr.py†L19-L68】
- File/proof validation: photo geofence/exif rules with hard 422 on violation; duplicate hash unique constraint; backend checks for invoice fields. 【F:app/services/proofs.py†L126-L198】【F:app/models/proof.py†L24-L28】【F:app/services/document_checks.py†L54-L170】
- Secrets/config: Settings pulled from `.env` with AI/OCR disabled by default; PSP webhook secrets optional but surfaced in health with fingerprints; OpenAI key required only when AI enabled. 【F:app/config.py†L35-L68】【F:.env.example†L1-L25】【F:app/routers/health.py†L104-L135】
- Logging/audit: AuditLog for proof submission/OCR/AI decisions, escrow reads, API key usage, PSP events; health avoids exposing raw secrets. 【F:app/services/proofs.py†L329-L405】【F:app/routers/escrow.py†L95-L106】【F:app/security.py†L115-L133】【F:app/services/psp_webhooks.py†L174-L228】

## G. Observability & operations
- Logging: central logger via `app.core.logging` and module loggers; AI/OCR and proof flows log statuses and failures. 【F:app/services/invoice_ocr.py†L179-L218】【F:app/services/ai_proof_advisor.py†L436-L507】【F:app/services/proofs.py†L419-L453】
- HTTP error handling: services raise HTTPException with structured error codes; health degrades on DB/migration issues. 【F:app/services/proofs.py†L173-L197】【F:app/routers/health.py†L111-L135】
- Alembic migrations health: multiple revisions including AI fields, AI score numeric conversion, invoice fields, scheduler lock, and PSP provider fields; health compares current DB head vs expected. 【F:alembic/versions/013024e16da9_add_ai_fields_to_proofs.py†L17-L51】【F:alembic/versions/c7f3d2f1fb35_change_ai_score_to_numeric.py†L17-L31】【F:alembic/versions/c6f0c1c0b8f4_add_invoice_fields_to_proofs.py†L14-L39】【F:app/routers/health.py†L64-L89】
- Deployment specifics: optional scheduler activated via env flags with lock TTL; settings cache TTL fixed at 60s; no executed migration/test commands in this audit (static inference only). 【F:app/main.py†L64-L134】【F:app/config.py†L96-L116】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority (P0/P1/P2) | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Monetary geofence precision | Geofence lat/lng/radius stored as Float leading to imprecise distance validation and potential wrongful approvals/rejections. | Medium | Medium | P0 | Migrate geofence fields to `Numeric(9,6)` with Decimal math, adjust haversine to Decimal, add migration. 【F:app/models/milestone.py†L56-L59】【F:app/services/proofs.py†L137-L180】 |
| R1b | Invoice normalization hardness | Invoice normalization raises 422 and blocks submission even when OCR absent; no retry guidance. | Medium | Medium | P1 | Convert to soft failure path pushing to manual review with audit flag, or return detailed error codes; add client guidance. 【F:app/services/proofs.py†L102-L120】 |
| R2 | PSP webhook secret freshness | Secrets cached for 60s and drift window fixed; rotation may lag and replay window broad. | High | Low | P0 | Bypass cache for webhook path or reduce TTL; enforce presence of secret in non-dev; allow configurable drift and persist processed event IDs with expiry. 【F:app/config.py†L96-L116】【F:app/services/psp_webhooks.py†L100-L171】 |
| R3 | Audit trail gaps | Escrow state transitions lack dedicated AuditLog entries except read; scheduler events not audited. | Medium | Medium | P1 | Add audit entries for delivery/approve/reject/deadline actions and scheduler lock changes; expose audit export endpoint. 【F:app/routers/escrow.py†L45-L86】【F:app/services/scheduler_lock.py†L36-L116】 |
| R4 | FastAPI lifespan dependency | Scheduler lock runs in lifespan; failures during shutdown could leave stale lock and no per-worker health endpoint. | Medium | Low | P1 | Add robust shutdown try/finally releasing lock, heartbeat failure alerts, and document single-runner requirement. 【F:app/main.py†L64-L134】 |
| R5 | AI safety defaults | AI circuit breaker is per-process; missing API key still increments errors; AI enabled flag might be toggled without persistence; sensitive metadata masking relies on pattern list. | Medium | Medium | P0 | Persist AI metrics, expose breaker state in health, hard-fail when AI enabled without key, expand masking allowlist tests, and store breaker counters in DB/Redis. 【F:app/services/ai_proof_advisor.py†L436-L507】【F:app/utils/masking.py†L66-L132】 |
| R6 | OCR robustness | OCR invoked with empty bytes and synchronous path; enabling real provider could block request threads. | Medium | Low | P2 | Offload OCR to background task or worker, add payload size checks, and avoid calling when metadata already complete. 【F:app/services/proofs.py†L87-L99】【F:app/services/invoice_ocr.py†L179-L218】 |
| R7 | Client-writable AI fields | AI fields are server-only in model but ensure schemas don’t accept them; verify migrations align. | High | Low | P0 | Keep AI fields out of creation schema (current behavior) and add DB constraint/migration to default null; add tests verifying client cannot set AI columns. 【F:app/models/proof.py†L39-L49】【F:app/schemas/proof.py†L5-L38】 |

## I. AI Proof Advisor, OCR & risk scoring (dedicated section)
### I.1 AI architecture
- Config defaults: AI_PROOF_ADVISOR_ENABLED False, provider/model/timeouts defined; OpenAI key optional when disabled. Invoice OCR defaults to disabled with dummy provider. 【F:app/config.py†L54-L68】【F:.env.example†L10-L25】
- Modules: feature flags (ai_proof_flags), advisory service with masking and circuit breaker (ai_proof_advisor), backend document checks (document_checks), OCR normalization/enrichment (invoice_ocr). 【F:app/services/ai_proof_flags.py†L10-L31】【F:app/services/ai_proof_advisor.py†L65-L507】【F:app/services/document_checks.py†L36-L170】【F:app/services/invoice_ocr.py†L179-L305】

### I.2 AI integration into proof flows
- PHOTO proofs: after EXIF/geofence validation, optional AI call builds context (mandate/backend/doc metadata), masks sensitive fields, and stores ai_assessment in metadata plus AI columns; failures are logged without blocking auto-approval. 【F:app/services/proofs.py†L137-L244】【F:app/services/ai_proof_advisor.py†L445-L496】
- NON-PHOTO proofs: always manual review; backend_checks computed and passed to AI advisor if enabled; AI result stored in metadata and columns. 【F:app/services/proofs.py†L245-L355】
- Storage: ai_risk_level/ai_score/flags/explanation/checked_at set on Proof; ai_reviewed_by/at set during decisions; AI metadata masked on response. 【F:app/services/proofs.py†L329-L355】【F:app/services/proofs.py†L458-L513】【F:app/routers/proofs.py†L16-L54】

### I.3 OCR & backend_checks
- OCR: run_invoice_ocr_if_enabled uses feature flag/provider mapping, returns disabled/error structure, increments stats, and normalizes via Pydantic; enrich_metadata_with_invoice_ocr avoids overwriting user-provided fields and logs status. 【F:app/services/invoice_ocr.py†L179-L218】【F:app/services/invoice_ocr.py†L274-L305】
- Backend checks: compute_document_backend_checks compares expected amount/currency/IBAN/date/supplier with metadata, returning structured signals without raising. 【F:app/services/document_checks.py†L36-L170】
- Integration: submit_proof calls backend checks for non-photo proofs and passes results into AI context; invoice normalization errors raise 422 before AI. 【F:app/services/proofs.py†L87-L123】【F:app/services/proofs.py†L245-L285】

### I.4 AI/OCR-specific risks
| ID | Domain (AI/OCR) | Risk | Impact | Likelihood | Priority | Recommended fix |
| --- | --- | --- | --- | --- | --- | --- |
| AI1 | Circuit breaker locality | Per-process counters may allow AI thrash across workers. | Medium | Medium | P0 | Persist counters/metrics centrally and expose breaker state in health. 【F:app/services/ai_proof_advisor.py†L436-L507】 |
| AI2 | Sensitive metadata masking scope | Masking relies on patterns; unexpected fields could leak to AI provider. | High | Medium | P0 | Enforce allowlist-based masking and add unit tests for new fields (IBAN masks, supplier data). 【F:app/utils/masking.py†L66-L132】 |
| AI3 | OCR call with empty bytes | OCR invoked even without uploaded file bytes, adding latency and potential provider errors. | Medium | Medium | P1 | Skip OCR when payload lacks file content; add timeout and async worker. 【F:app/services/proofs.py†L87-L99】【F:app/services/invoice_ocr.py†L179-L218】 |
| AI4 | AI optionality | AI enabled but OpenAI key missing returns fallback warning and increments error counters. | Low | Medium | P1 | When AI enabled, fail fast at startup if key missing or automatically disable with audit log. 【F:app/services/ai_proof_advisor.py†L456-L470】 |
| AI5 | Client visibility of AI fields | AI fields exposed on read but not writable; ensure schemas stay server-only and DB defaults null. | Medium | Low | P2 | Add schema tests; enforce DB defaults/constraints. 【F:app/models/proof.py†L39-L49】【F:app/schemas/proof.py†L5-L38】 |

## J. Roadmap to a staging-ready MVP
- P0 checklist (blocking):
  - Convert milestone geofence floats to Decimal/Numeric and update haversine math to avoid precision errors. 【F:app/models/milestone.py†L56-L59】【F:app/services/proofs.py†L137-L180】
  - Harden PSP webhook secret handling: reduce settings cache TTL for webhook path, enforce secret presence, tune drift window, and persist replay IDs. 【F:app/config.py†L96-L116】【F:app/services/psp_webhooks.py†L100-L171】
  - Centralize AI circuit breaker/metrics and tighten masking/allowlist before sending context to AI; ensure AI cannot enable without key. 【F:app/services/ai_proof_advisor.py†L436-L507】【F:app/utils/masking.py†L66-L132】
- P1 checklist (pre-pilot):
  - Make invoice normalization failures non-blocking or more user-guided; move OCR to async worker; add audit events for escrow lifecycle and scheduler actions. 【F:app/services/proofs.py†L102-L120】【F:app/services/invoice_ocr.py†L179-L218】【F:app/routers/escrow.py†L45-L86】
  - Document scheduler single-runner requirement and add shutdown safety for lock release. 【F:app/main.py†L64-L134】
  - Strengthen health endpoint to include AI circuit breaker state and OCR/AI call counters. 【F:app/routers/health.py†L104-L135】
- P2 checklist (comfort/scalability):
  - Refactor idempotency dependency reuse across routers; add pagination/search to user/API key endpoints. 【F:app/routers/transactions.py†L46-L68】【F:app/routers/users.py†L16-L98】
  - Expand observability with structured logging/correlation IDs and Sentry/Prometheus wiring if enabled. 【F:app/config.py†L51-L53】

**Verdict: NO-GO for a staging with 10 real users until P0 items (geofence precision, PSP webhook hardening, AI breaker/masking persistence) are addressed.**

## K. Verification evidence
- Alembic commands (not run): `alembic current`, `alembic heads`, `alembic history --verbose` would confirm DB head matches expected revision and include AI/OCR migrations noted above. Healthcheck code compares current vs expected head using `alembic_version` table. 【F:app/routers/health.py†L64-L89】
- Test suite structure (static): `pytest -q` would execute AI config/privacy/resilience, OCR normalization, proof flows, PSP webhook, scheduler lock, spend idempotency, health, and table existence tests listed in section E. 【F:tests/test_ai_config.py†L1-L44】【F:tests/test_invoice_ocr.py†L1-L140】【F:tests/test_psp_webhook.py†L1-L200】【F:tests/test_scheduler_lock.py†L1-L120】【F:tests/test_spend_idempotency.py†L1-L140】
- Key code references underpinning this audit include routers, services, models, and migrations cited throughout (e.g., AI advisor integration, OCR enrichment, geofence validation, security dependencies). 【F:app/services/proofs.py†L126-L355】【F:app/services/ai_proof_advisor.py†L436-L507】【F:app/services/invoice_ocr.py†L179-L305】【F:app/security.py†L33-L183】【F:alembic/versions/c6f0c1c0b8f4_add_invoice_fields_to_proofs.py†L14-L39】
