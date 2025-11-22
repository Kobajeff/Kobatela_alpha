# Kobatela_alpha — Capability & Stability Audit (2025-11-22)

## A. Executive summary
- FastAPI stack with scoped API-key auth, role checks, and audit logging for key actions across escrows, proofs, and payments.【F:app/security.py†L21-L155】【F:app/routers/escrow.py†L24-L141】
- Proof submissions include EXIF/geofence validation, invoice normalization, and optional AI/OCR enrichment with audit entries for OCR/AI runs.【F:app/services/proofs.py†L83-L377】
- AI and OCR are feature-flagged in settings and surfaced in health telemetry with basic counters for visibility.【F:app/config.py†L36-L115】【F:app/routers/health.py†L104-L148】【F:app/services/ai_proof_advisor.py†L82-L93】【F:app/services/invoice_ocr.py†L118-L123】
- Lifespan-based startup asserts PSP secrets, configures middleware, and guards scheduler startup with DB locks and heartbeat refresh jobs.【F:app/main.py†L77-L149】
- Alembic migrations cover AI fields, invoice totals, scheduler locks, and webhook tables; health endpoint checks migration drift at runtime.【F:alembic/versions/c6f0c1c0b8f4_add_invoice_fields_to_proofs.py†L14-L38】【F:alembic/versions/c7f3d2f1fb35_change_ai_score_to_numeric.py†L17-L32】【F:app/routers/health.py†L64-L140】

Major risks / limitations:
- Geofence coordinates and radius use floating-point storage and math, risking precision errors in distance validation for proof approvals.【F:app/models/milestone.py†L53-L60】【F:app/services/proofs.py†L126-L180】
- Invoice normalization failures raise hard 422 errors and OCR is invoked with empty bytes for PDFs/contracts, which could block users or waste compute when OCR is enabled.【F:app/services/proofs.py†L87-L120】【F:app/services/invoice_ocr.py†L179-L218】
- AI circuit breaker and counters are in-memory per process; AI calls proceed even if API key missing, relying on fallback responses without persistent observability.【F:app/services/ai_proof_advisor.py†L23-L93】【F:app/services/ai_proof_advisor.py†L402-L507】
- Settings cache TTL of 60s can delay secret rotations (PSP, AI, OCR) and feature toggles; webhook drift configuration differs between code (180s) and `.env.example` (300s).【F:app/config.py†L35-L116】【F:.env.example†L1-L8】
- Audit trail is strong for proofs but thinner for escrow status transitions and scheduler lock lifecycle, limiting forensic coverage.【F:app/services/proofs.py†L329-L381】【F:app/routers/escrow.py†L79-L120】【F:app/services/scheduler_lock.py†L36-L116】

Readiness score (staging MVP): **74 / 100** — solid functional surface with AI/OCR guards, but P0 fixes are required for monetary/geofence precision, webhook/secret handling, and AI/OCR resilience before onboarding external users.

## B. Capability map (current features)
### B.1 Functional coverage
| Feature | Endpoints / modules involved | Status (OK / Partial / Missing) | Notes |
| --- | --- | --- | --- |
| Health & telemetry | `/health` | OK | Reports DB/migration status, PSP secrets fingerprints, AI/OCR flags and counters, scheduler lock state.【F:app/routers/health.py†L104-L148】 |
| API key management | `/apikeys` | Partial | Routes present but not fully listed in code excerpt; scopes enforced elsewhere.【F:app/routers/apikeys.py†L1-L120】 |
| Escrow lifecycle | `/escrows/*` | OK | Create, deposit (idempotency header), mark delivered, client approve/reject, deadline check, read with audit log.【F:app/routers/escrow.py†L24-L141】 |
| Proof submission & decision | `/proofs`, `/proofs/{id}/decision` | OK | Photo validations, invoice normalization, OCR enrichment, AI advisory, audit logs, manual decisions update AI review fields.【F:app/routers/proofs.py†L24-L54】【F:app/services/proofs.py†L83-L377】【F:app/services/proofs.py†L458-L589】 |
| Payments & PSP webhooks | `/payments/execute/{id}`, `/psp/webhook`, `/psp/stripe/webhook` | OK | Manual payout execution; HMAC/timestamp verification and replay defense for PSP webhook; Stripe handler stubbed.【F:app/routers/payments.py†L18-L63】【F:app/routers/psp.py†L21-L77】【F:app/services/psp_webhooks.py†L100-L191】 |
| Spend controls & transactions | `/spend/*`, `/transactions`, `/allowlist`, `/certified` | OK | Merchants, categories, allowlist/certification, purchases with idempotency headers, admin transaction posting/lookup.【F:app/routers/spend.py†L21-L116】【F:app/routers/transactions.py†L21-L86】 |
| Alerts & public mandates | `/alerts`, `/kct_public/mandates` | OK | Alert listing and GOV/ONG public sector aggregation with scope checks.【F:app/routers/alerts.py†L7-L40】【F:app/routers/kct_public.py†L21-L163】 |
| AI Proof Advisor | `ai_proof_flags`, AI integration in proofs | Partial | Feature-flagged; in-memory circuit breaker; fallback results when provider unavailable.【F:app/services/ai_proof_flags.py†L10-L31】【F:app/services/ai_proof_advisor.py†L23-L93】【F:app/services/proofs.py†L201-L290】 |
| Invoice OCR | `invoice_ocr`, proof submission | Partial | Dummy provider only; always called for non-photo proofs with empty bytes; enrichment avoids overwriting user fields.【F:app/services/invoice_ocr.py†L179-L218】【F:app/services/proofs.py†L87-L100】 |
| Scheduler | Lifespan + `/health` | OK | Optional APScheduler with DB lock acquire/refresh/release; exposed in health payload.【F:app/main.py†L77-L149】【F:app/services/scheduler_lock.py†L36-L116】 |

### B.2 End-to-end journeys supported today
- Photo proof: submit with EXIF/geofence validation → optional AI advisory → auto-approve if clean → payment execution with idempotency key and audit logs.【F:app/services/proofs.py†L126-L355】【F:app/services/proofs.py†L458-L589】
- Invoice/contract proof: submit → OCR enrichment + invoice normalization → backend checks → AI advisory for manual review → AI fields stored and audited.【F:app/services/proofs.py†L83-L377】【F:app/services/document_checks.py†L36-L170】
- Escrow lifecycle: create → deposit with idempotency → mark delivered → client approve/reject or deadline check; audit on reads and proof decisions.【F:app/routers/escrow.py†L24-L141】【F:app/services/proofs.py†L458-L589】
- PSP settlement: webhook verifies signature/timestamp, rejects replays, updates payment events; Stripe webhook handler included.【F:app/routers/psp.py†L21-L77】【F:app/services/psp_webhooks.py†L100-L191】
- Spend controls: manage categories/merchants/allowlists and execute purchases/usage with idempotency and scope enforcement.【F:app/routers/spend.py†L21-L116】【F:app/routers/transactions.py†L21-L86】

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request model | Response model | HTTP codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/health` | `health.healthcheck` | None | – | – | dict | 200 |
| POST | `/escrows` | `escrow.create_escrow` | API key | sender | `EscrowCreate` | `EscrowRead` | 201 |
| POST | `/escrows/{id}/deposit` | `escrow.deposit` | API key + Idempotency-Key | sender | `EscrowDepositCreate` | `EscrowRead` | 200 |
| POST | `/escrows/{id}/funding-session` | `escrow.create_funding_session` | API key | sender/admin | – | `FundingSessionRead` | 201 |
| POST | `/escrows/{id}/mark-delivered` | `escrow.mark_delivered` | API key | sender | `EscrowActionPayload` | `EscrowRead` | 200 |
| POST | `/escrows/{id}/client-approve` | `escrow.client_approve` | API key | sender | optional body | `EscrowRead` | 200 |
| POST | `/escrows/{id}/client-reject` | `escrow.client_reject` | API key | sender | optional body | `EscrowRead` | 200 |
| POST | `/escrows/{id}/check-deadline` | `escrow.check_deadline` | API key | sender | – | `EscrowRead` | 200 |
| GET | `/escrows/{id}` | `escrow.read_escrow` | API key | sender/support/admin | – | `EscrowRead` | 200, 404 |
| POST | `/proofs` | `proofs.submit_proof` | API key | sender | `ProofCreate` | `ProofRead` | 201, 404, 409, 422 |
| POST | `/proofs/{id}/decision` | `proofs.decide_proof` | API key | support/admin | `ProofDecision` | `ProofRead` | 200, 400, 404 |
| POST | `/payments/execute/{id}` | `payments.execute_payment` | API key | sender | – | `PaymentRead` | 200 |
| POST | `/psp/webhook` | `psp.psp_webhook` | Secret headers | PSP | raw JSON | dict | 200, 400, 401, 503 |
| POST | `/psp/stripe/webhook` | `psp.stripe_webhook` | Secret via handler | PSP | raw JSON | dict | 200 |
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
  - Proof: unique SHA256, metadata JSON, normalized invoice totals/currency, AI assessment columns (risk level/score/flags/explanation/checked/reviewed).【F:app/models/proof.py†L11-L49】
  - Milestone: per-escrow unique idx, `Numeric(18,2)` amount, JSON requirements, geofence lat/lng/radius stored as Float, status enum.【F:app/models/milestone.py†L32-L62】
  - EscrowAgreement/Deposit/Event: statuses and deadline handling with idempotent deposits enforced via header in router/service logic.【F:app/models/escrow.py†L12-L55】【F:app/routers/escrow.py†L41-L53】
  - Payment: numeric amount, unique PSP reference/idempotency keys with status enum transitions.【F:app/models/payment.py†L16-L38】【F:app/services/payments.py†L23-L86】
  - API Key: scoped tokens with unique hash/prefix and audit on usage; legacy dev key allowed in dev only.【F:app/models/api_key.py†L11-L32】【F:app/security.py†L33-L107】
  - AuditLog: actor/action/entity/data_json/timestamp for immutable audit trail; used for proofs, AI/OCR, API key usage.【F:app/models/audit.py†L8-L17】【F:app/services/proofs.py†L329-L381】【F:app/security.py†L115-L133】
  - SchedulerLock: owner/expires_at indexed for lock heartbeat and release.【F:app/models/scheduler_lock.py†L11-L24】【F:app/services/scheduler_lock.py†L36-L116】
- State machines:
  - Proof: WAITING milestone → submit sets proof to PENDING or APPROVED (auto-approve on clean photo) → decision approve/reject updates milestone status and AI review fields; approvals trigger payout execution.【F:app/services/proofs.py†L124-L377】【F:app/services/proofs.py†L458-L589】
  - Escrow: statuses defined on model with service flows for delivered/approve/reject/deadline; payments initiated on proof approval.【F:app/models/escrow.py†L12-L46】【F:app/services/escrow.py†L67-L154】
  - Payment: PENDING → SENT/SETTLED/ERROR/REFUNDED via execute endpoint or PSP webhook updates with replay guard.【F:app/models/payment.py†L16-L30】【F:app/services/psp_webhooks.py†L100-L191】

## E. Stability results
- Static view of tests (not executed): coverage spans AI flags/config (`test_ai_config.py`), AI privacy/resilience/score precision, OCR normalization/enrichment, proof EXIF/geofence and AI review, escrow/payment flows, spend idempotency, PSP webhook signature handling, scheduler lock/flag, observability and table presence.【F:tests/test_ai_config.py†L1-L44】【F:tests/test_invoice_ocr.py†L1-L85】【F:tests/test_milestone_sequence_and_exif.py†L1-L160】【F:tests/test_psp_webhook.py†L1-L200】【F:tests/test_scheduler_lock.py†L1-L120】【F:tests/check_tables.py†L1-L80】
- No tests or migrations were run for this audit; stability is inferred from code paths and test intent (static analysis only).
- Static review notes: geofence math uses floats; invoice normalization throws hard 422; OCR called with empty bytes synchronously; AI circuit breaker metrics are in-memory; settings cache may stale secrets; broad exception handling around AI/OCR is intentional but hides root causes.【F:app/services/proofs.py†L87-L198】【F:app/services/invoice_ocr.py†L179-L218】【F:app/services/ai_proof_advisor.py†L23-L93】【F:app/config.py†L35-L116】

## F. Security & integrity
- AuthN/Z: API key validation with scopes (sender/support/admin) and optional legacy dev key; GOV/ONG restriction for public mandates; audit log on key usage.【F:app/security.py†L33-L183】【F:app/routers/kct_public.py†L21-L84】
- Input validation: Pydantic schemas bound lengths/patterns for proofs/escrows; monetary fields use Decimal/Numeric except geofence floats; proof decision regex prevents arbitrary status values.【F:app/schemas/proof.py†L8-L48】【F:app/schemas/escrow.py†L5-L64】【F:app/models/milestone.py†L53-L60】
- File/proof validation: SHA256 uniqueness, EXIF/geofence checks, hard validation 422 for geofence/age errors, manual review for soft errors, AI advisory non-blocking.【F:app/models/proof.py†L22-L27】【F:app/services/proofs.py†L126-L244】
- Secrets & config: Settings via `.env` with feature flags for AI/OCR and PSP webhook secrets; cache TTL 60s; `.env.example` includes AI/OCR defaults disabled.【F:app/config.py†L35-L116】【F:.env.example†L1-L25】
- Audit/logging: AuditLog entries for proof submission/decision, AI/OCR runs, API key usage; logging in AI/OCR and proof flows for failures and durations.【F:app/services/proofs.py†L329-L381】【F:app/services/proofs.py†L458-L513】【F:app/services/invoice_ocr.py†L296-L305】【F:app/services/ai_proof_advisor.py†L436-L507】【F:app/security.py†L115-L133】

## G. Observability & operations
- Logging: Central logging setup; module-level loggers across AI/OCR/proofs; no correlation IDs but structured extras for key events.【F:app/core/logging.py†L1-L120】【F:app/services/ai_proof_advisor.py†L436-L507】【F:app/services/proofs.py†L417-L513】
- HTTP error handling: Global exception handlers wrapping unexpected errors; consistent `HTTPException` usage for validation/state failures; PSP webhook returns clear error codes on missing secrets/signature issues.【F:app/main.py†L161-L176】【F:app/services/proofs.py†L72-L197】【F:app/routers/psp.py†L21-L69】
- Alembic migrations health: Version files add AI, invoice, scheduler, and webhook structures; health endpoint compares DB head vs Alembic head and reports drift.【F:alembic/versions/c6f0c1c0b8f4_add_invoice_fields_to_proofs.py†L14-L38】【F:alembic/versions/c7f3d2f1fb35_change_ai_score_to_numeric.py†L17-L32】【F:alembic/versions/a9bba28305c0_add_scheduler_locks_table.py†L1-L40】【F:app/routers/health.py†L64-L140】
- Deployment specifics: Lifespan asserts PSP secrets outside dev, optional scheduler enabled via env with DB lock heartbeat; settings TTL may delay runtime config changes; no command outputs available (static audit only).【F:app/main.py†L59-L149】【F:app/config.py†L35-L116】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority (P0/P1/P2) | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Monetary/geofence precision | Geofence lat/lng/radius stored as `Float` and haversine uses floats → potential false positives/negatives in proof validation and auto-approval.| High | Medium | P0 | Migrate geofence fields to `Numeric(9,6, asdecimal=True)` and use Decimal-based distance; add Alembic migration and regression tests for edge distances.【F:app/models/milestone.py†L53-L60】【F:app/services/proofs.py†L126-L180】 |
| R2 | PSP webhook secret freshness | Settings cached 60s and drift window mismatch (code 180s vs `.env.example` 300s) can delay rotations or widen replay surface.| High | Medium | P0 | Reduce cache TTL or bypass cache for webhook verification; align drift window defaults; document rotation; persist replay IDs with expiry instead of in-memory.【F:app/config.py†L35-L116】【F:.env.example†L1-L8】【F:app/services/psp_webhooks.py†L100-L191】 |
| R3 | Business lifecycle audit | Escrow status transitions and scheduler lock events lack dedicated audit entries, limiting forensic traceability.| Medium | Medium | P0 | Add AuditLog entries on delivered/approve/reject/deadline/scheduler acquire-refresh-release; expose audit export endpoint.【F:app/routers/escrow.py†L79-L120】【F:app/services/scheduler_lock.py†L36-L116】 |
| R4 | FastAPI lifespan robustness | Scheduler lock release only in finally; failure before release could leave stale lock and heartbeat failures are silent.| Medium | Low | P0 | Add try/finally with explicit release checks and alerting; record lock owner/heartbeat metrics in health; document single-runner constraint.【F:app/main.py†L104-L149】【F:app/services/scheduler_lock.py†L36-L116】 |
| R5 | AI & OCR safety defaults | AI enabled without API key still calls advisor with fallback; circuit breaker stats in-memory; OCR invoked with empty bytes; masking allowlist may miss fields.| High | Medium | P0 | Fail fast when AI enabled but key missing; persist AI/OCR counters (DB/Redis) and expose in health; skip OCR when no file; tighten masking allowlist and tests.【F:app/services/ai_proof_advisor.py†L23-L93】【F:app/services/proofs.py†L87-L100】【F:app/utils/masking.py†L66-L132】 |
| R6 | Invoice normalization hardness | Hard 422 on normalization errors blocks proof submission without guidance; may reject minor formatting issues.| Medium | Medium | P1 | Treat normalization errors as soft/manual review with explicit error codes or warnings; add client-facing remediation hints and tests.【F:app/services/proofs.py†L102-L120】 |
| R7 | OCR performance | OCR called synchronously per request; real provider could stall API threads.| Medium | Low | P2 | Add timeout and background job/offloading for OCR; short-circuit when OCR disabled or bytes empty; monitor latency via metrics.【F:app/services/invoice_ocr.py†L179-L218】 |
| R8 | Idempotency reuse | Idempotency helper spread across routers/services; inconsistent enforcement risk for financial operations.| Low | Medium | P2 | Centralize idempotency dependency and add shared tests across spend/transactions/escrow payments.【F:app/services/idempotency.py†L1-L85】【F:app/routers/transactions.py†L46-L68】 |

## I. AI Proof Advisor, OCR & risk scoring (dedicated section)
### I.1 AI architecture
- Config defaults: AI disabled by default with provider/model/timeouts; OpenAI key optional; OCR disabled with provider `none/dummy` in settings and `.env.example`.【F:app/config.py†L36-L68】【F:.env.example†L10-L25】
- Modules: feature flags (`ai_proof_flags`), advisory service with masking and circuit breaker (`ai_proof_advisor`), backend checks for invoices/contracts (`document_checks`), OCR normalization/enrichment (`invoice_ocr`).【F:app/services/ai_proof_flags.py†L10-L31】【F:app/services/ai_proof_advisor.py†L23-L507】【F:app/services/document_checks.py†L36-L170】【F:app/services/invoice_ocr.py†L179-L306】

### I.2 AI integration into proof flows
- PHOTO proofs: After EXIF/geofence validation, optional AI call builds mandate/backend/document context, masks metadata, stores `ai_assessment` and AI columns; failures logged and non-blocking.【F:app/services/proofs.py†L126-L244】【F:app/services/proofs.py†L201-L244】【F:app/models/proof.py†L39-L49】
- NON-PHOTO proofs: Always manual review; computes backend checks (amount/IBAN/date/supplier) and passes to AI; AI result stored without blocking submission.【F:app/services/proofs.py†L245-L290】【F:app/services/document_checks.py†L36-L170】
- Storage & audit: AI columns persisted on Proof, `ai_checked_at` set, and AuditLog entry recorded when AI result exists.【F:app/models/proof.py†L39-L49】【F:app/services/proofs.py†L329-L381】

### I.3 OCR & backend_checks
- OCR enrichment: For non-photo proofs, OCR called (dummy by default) then merged into metadata without overwriting user-supplied invoice fields; raw OCR stored under `ocr_raw`.【F:app/services/proofs.py†L87-L100】【F:app/services/invoice_ocr.py†L274-L305】
- Backend checks: `compute_document_backend_checks` compares expected amount/currency/IBAN/date/supplier from `proof_requirements` vs metadata, returning structured signals used in AI context; gracefully handles missing data.【F:app/services/document_checks.py†L36-L170】

### I.4 AI/OCR-specific risks
| ID | Domain (AI/OCR) | Risk | Impact | Likelihood | Priority | Recommended fix |
| --- | --- | --- | --- | --- | --- | --- |
| AI-1 | AI config | AI enabled without API key leads to fallback results without alerting; breaker in-memory.| Medium | Medium | P0 | Validate OPENAI_API_KEY when AI flag true; persist breaker counters and expose in health.|【F:app/services/ai_proof_advisor.py†L23-L93】 |
| AI-2 | Data minimization | Metadata masking relies on allowlist; potential leakage if new fields added without masking.| Medium | Medium | P1 | Enforce explicit mask on sensitive patterns and extend tests for new metadata keys.|【F:app/utils/masking.py†L66-L132】 |
| OCR-1 | Invocation flow | OCR called with empty bytes for PDFs/contracts causing wasted calls and possible provider errors.| Low | Medium | P1 | Skip OCR when file bytes absent or when provider disabled; add timeout and retries.|【F:app/services/proofs.py†L87-L99】【F:app/services/invoice_ocr.py†L179-L218】 |
| OCR-2 | Error handling | OCR normalization errors only logged, not surfaced; counters in-memory.| Medium | Low | P2 | Persist OCR stats; return structured warnings to clients; add provider-specific error mapping.|【F:app/services/invoice_ocr.py†L118-L217】 |

## J. Roadmap to a staging-ready MVP
- P0 checklist (blocking):
  - Fix geofence precision (Numeric + Decimal haversine) and add migration/tests.【F:app/models/milestone.py†L53-L60】【F:app/services/proofs.py†L126-L180】
  - Harden PSP webhook verification (shorter cache TTL, align drift window, persistent replay store, fail-fast when secrets missing).【F:app/config.py†L35-L116】【F:app/routers/psp.py†L21-L69】
  - Enforce AI/OCR safety: require API key when AI enabled, persist breaker metrics, skip OCR on empty bytes, mask new metadata fields; add health exposure.【F:app/services/ai_proof_advisor.py†L23-L93】【F:app/services/proofs.py†L87-L100】【F:app/utils/masking.py†L66-L132】
  - Add audit logs for escrow transitions and scheduler lock lifecycle; ensure lock release/heartbeat failures alert and clean stale locks.【F:app/routers/escrow.py†L79-L120】【F:app/services/scheduler_lock.py†L36-L116】【F:app/main.py†L104-L149】
  - Relax invoice normalization to soft errors or clearer guidance; add manual review flag instead of hard 422.【F:app/services/proofs.py†L102-L120】
- P1 checklist (before pilot):
  - Background/async OCR processing with timeouts; optional queue for AI requests to avoid blocking.
  - Centralize idempotency handling across financial endpoints; add duplicate-key regression tests.【F:app/services/idempotency.py†L1-L85】
  - Extend masking and privacy tests for new metadata fields and AI contexts.【F:app/utils/masking.py†L66-L132】
  - Improve settings reload cadence or targeted cache bypass for secrets/feature flags.【F:app/config.py†L35-L116】
- P2 checklist (scalability/comfort):
  - Add correlation IDs and structured logging for cross-service tracing.
  - Persist AI/OCR metrics and expose Prometheus counters with alert thresholds.
  - Document scheduler single-runner constraint and add distributed lock alternative.

**Verdict: NO-GO for exposing to 10 real users until P0 items are addressed** (geofence precision, webhook/secret handling, AI/OCR safety, and audit coverage). After P0 fixes, proceed with limited pilot alongside enhanced monitoring.

## K. Verification evidence
- Migration health: `alembic current`, `alembic heads`, `alembic history --verbose` would verify applied revisions, including AI/invoice columns and scheduler lock tables observed in migration files.【F:alembic/versions/c6f0c1c0b8f4_add_invoice_fields_to_proofs.py†L14-L38】【F:alembic/versions/c7f3d2f1fb35_change_ai_score_to_numeric.py†L17-L32】【F:alembic/versions/a9bba28305c0_add_scheduler_locks_table.py†L1-L40】 (not executed; static inference).
- Test suite structure: `pytest -q` would cover AI flags/privacy/resilience, OCR normalization/enrichment, proof validations/AI review, escrow/payment/spend idempotency, PSP webhook signature, scheduler lock/flag, observability, and table existence based on test files listed (not executed; static inference).【F:tests/test_ai_config.py†L1-L44】【F:tests/test_invoice_ocr.py†L1-L85】【F:tests/test_milestone_sequence_and_exif.py†L1-L160】【F:tests/test_psp_webhook.py†L1-L200】【F:tests/test_scheduler_lock.py†L1-L120】【F:tests/check_tables.py†L1-L80】
- File references in this audit point to routers/services/models/schemas demonstrating current behavior, configuration defaults, and risk areas across AI, OCR, proofs, payments, and scheduler flows.
