# Kobatela_alpha — Capability & Stability Audit (2025-11-10)

## A. Executive summary
- Strength: Domain services normalise money to `Decimal`, enforce idempotency keys, and emit timeline events across escrow, transactions, and payouts, reducing double-booking risk.【F:app/services/escrow.py†L19-L188】【F:app/services/transactions.py†L25-L97】【F:app/services/payments.py†L84-L277】
- Strength: Proof intake includes EXIF, GPS, and geofence validation before touching milestone state, with auto-approval only when hard validation passes.【F:app/services/proofs.py†L45-L246】【F:app/services/rules.py†L15-L107】
- Strength: Financial mutations write structured audit records (transactions, usage spends, payout execution) for later review.【F:app/services/transactions.py†L73-L86】【F:app/services/usage.py†L46-L235】【F:app/services/payments.py†L237-L277】
- Strength: Schema-level constraints protect monetary tables (check constraints, unique idempotency keys, indexed statuses).【F:app/models/escrow.py†L23-L68】【F:app/models/payment.py†L21-L38】【F:app/models/allowed_payee.py†L11-L32】【F:alembic/versions/baa4932d9a29_0001_init_schema.py†L16-L199】
- Strength: Regression suite (21 tests) and successful migrations give fast feedback on core flows.【3f08df†L1-L2】【1638b0†L1-L3】
- Risk: Purchases persist `Numeric(..., asdecimal=False)` into a Python `float`, introducing rounding drift in spend ledgers (P0 blocking for real money).【F:app/models/spend.py†L64-L80】
- Risk: PSP webhook endpoint has no auth dependency and defaults the HMAC secret to blank at import time, allowing unauthenticated replay or forgery (P0).【F:app/routers/psp.py†L15-L45】【F:app/services/psp_webhooks.py†L20-L35】
- Risk: App still wires legacy `@app.on_event` handlers when `use_lifespan` flag is flipped, violating the "lifespan-only" requirement and risking drift between startup paths (P0).【F:app/main.py†L36-L55】
- Risk: Escrow lifecycle actions (create, mark delivered/released/rejected) emit timeline events but no audit trail, leaving critical state changes unaudited (P0 by policy).【F:app/services/escrow.py†L36-L180】
- Risk: Single global API key guard lacks user identity, rotation strategy, or rate limiting, so any leak grants full control (P1).【F:app/security.py†L7-L21】【F:app/routers/__init__.py†L10-L19】
- Readiness score: **45 / 100** — functional flows exist, but float money storage, unauthenticated PSP ingress, and missing audits block safe external testing.

## B. Capability map (current, concrete)

### B.1 Feature coverage
| Feature | Implemented endpoints/modules | Status | Notes |
| --- | --- | --- | --- |
| Health & metadata | `GET /health` → `health.healthcheck` | Implemented | Simple uptime probe without dependencies.【F:app/routers/health.py†L4-L11】 |
| User onboarding | `POST /users`, `GET /users/{id}` | Implemented | Creates basic user records guarded by global API key.【F:app/routers/users.py†L11-L31】 |
| Alerts listing | `GET /alerts` | Implemented | Filters by type and surfaces operational alerts.【F:app/routers/alerts.py†L11-L19】 |
| Escrow lifecycle | Escrow router + service | Partial | CRUD and state transitions exist, but no audit log and no auth beyond API key.【F:app/routers/escrow.py†L12-L63】【F:app/services/escrow.py†L36-L190】 |
| Escrow funding | `POST /escrows/{id}/deposit` | Implemented | Idempotent deposits update totals and emit events.【F:app/routers/escrow.py†L20-L27】【F:app/services/escrow.py†L65-L118】 |
| Allowlist & certification | `POST /allowlist`, `POST /certified` | Implemented | Adds allowlist rows and certification levels with logging.【F:app/routers/transactions.py†L27-L63】 |
| Restricted transactions | `POST /transactions` | Implemented | Enforces allowlist/certification, writes audit + alert on rejection.【F:app/routers/transactions.py†L66-L75】【F:app/services/transactions.py†L34-L86】 |
| Spend controls | `/spend/categories`, `/spend/merchants`, `/spend/allow`, `/spend/purchases` | Partial | Category/merchant setup and idempotent purchases available; purchase amounts stored as float.【F:app/routers/spend.py†L22-L46】【F:app/models/spend.py†L64-L80】 |
| Usage payees & spend | `/spend/allowed`, `POST /spend` | Implemented | Adds payees with limits and executes idempotent spends with audits.【F:app/routers/spend.py†L49-L105】【F:app/services/usage.py†L23-L235】 |
| Proof submission & review | `/proofs`, `/proofs/{id}/decision` | Implemented | Validates EXIF/geofence, auto-pays when safe, handles decisions.【F:app/routers/proofs.py†L11-L33】【F:app/services/proofs.py†L45-L411】 |
| Payment execution | `POST /payments/execute/{payment_id}` | Partial | Executes payouts with audits, but relies on prior record creation and inherits PSP risks.【F:app/routers/payments.py†L10-L17】【F:app/services/payments.py†L84-L303】 |
| PSP webhook ingestion | `POST /psp/webhook` | Partial | Persists events and updates payments but lacks auth/secret management.【F:app/routers/psp.py†L15-L45】【F:app/services/psp_webhooks.py†L20-L129】 |

### B.2 Supported end-to-end flows (today)
- **Allowlisted transfer**: create users → add allowlist entry (`POST /allowlist`) → post restricted transaction with idempotency header to record completion + audit.【F:app/routers/users.py†L11-L31】【F:app/routers/transactions.py†L27-L75】【F:app/services/transactions.py†L25-L86】
- **Escrow with milestone proof**: create escrow → deposit funds → submit proof with valid metadata → auto payout and milestone advancement → optional manual approval path.【F:app/routers/escrow.py†L12-L63】【F:app/services/escrow.py†L36-L190】【F:app/routers/proofs.py†L11-L33】【F:app/services/proofs.py†L45-L318】
- **Conditional usage spend**: configure spend category/merchant → allow usage rules → add allowed payee → spend with per-day/total enforcement and audit trail.【F:app/routers/spend.py†L22-L105】【F:app/services/spend.py†L19-L119】【F:app/services/usage.py†L23-L235】
- **Payment settlement feedback**: execute payout via `/payments/execute/{id}` → PSP webhook updates status to `SETTLED`/`ERROR` while writing audit events.【F:app/routers/payments.py†L10-L17】【F:app/services/payments.py†L205-L303】【F:app/services/psp_webhooks.py†L38-L129】

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request | Response | Codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | /health | `health.healthcheck` | None | n/a | – | `dict[str,str]` | 200【F:app/routers/health.py†L4-L11】 |
| POST | /users | `users.create_user` | API key | n/a | `UserCreate` | `UserRead` | 201【F:app/routers/users.py†L11-L22】 |
| GET | /users/{user_id} | `users.get_user` | API key | n/a | Path ID | `UserRead` | 200/404【F:app/routers/users.py†L24-L31】 |
| GET | /alerts | `alerts.list_alerts` | API key | n/a | Query `type` | `list[AlertRead]` | 200【F:app/routers/alerts.py†L11-L19】 |
| POST | /escrows | `escrow.create_escrow` | API key | n/a | `EscrowCreate` | `EscrowRead` | 201【F:app/routers/escrow.py†L12-L17】 |
| POST | /escrows/{id}/deposit | `escrow.deposit` | API key | n/a | `EscrowDepositCreate` + Idempotency-Key | `EscrowRead` | 200【F:app/routers/escrow.py†L20-L27】 |
| POST | /escrows/{id}/mark-delivered | `escrow.mark_delivered` | API key | n/a | `EscrowActionPayload` | `EscrowRead` | 200【F:app/routers/escrow.py†L30-L33】 |
| POST | /escrows/{id}/client-approve | `escrow.client_approve` | API key | n/a | Optional body | `EscrowRead` | 200【F:app/routers/escrow.py†L35-L41】 |
| POST | /escrows/{id}/client-reject | `escrow.client_reject` | API key | n/a | Optional body | `EscrowRead` | 200【F:app/routers/escrow.py†L44-L50】 |
| POST | /escrows/{id}/check-deadline | `escrow.check_deadline` | API key | n/a | Path ID | `EscrowRead` | 200【F:app/routers/escrow.py†L53-L55】 |
| GET | /escrows/{id} | `escrow.read_escrow` | API key | n/a | Path ID | `EscrowRead` | 200/404【F:app/routers/escrow.py†L58-L63】 |
| POST | /allowlist | `transactions.add_to_allowlist` | API key | n/a | `AllowlistCreate` | status dict | 201 |【F:app/routers/transactions.py†L27-L43】 |
| POST | /certified | `transactions.add_certification` | API key | n/a | `CertificationCreate` | status dict | 201 |【F:app/routers/transactions.py†L46-L63】 |
| POST | /transactions | `transactions.post_transaction` | API key | n/a | `TransactionCreate` + Idempotency-Key | `TransactionRead` | 201【F:app/routers/transactions.py†L66-L75】 |
| GET | /transactions/{id} | `transactions.get_transaction` | API key | n/a | Path ID | `TransactionRead` | 200/404【F:app/routers/transactions.py†L78-L87】 |
| POST | /spend/categories | `spend.create_category` | API key | n/a | `SpendCategoryCreate` | `SpendCategoryRead` | 201【F:app/routers/spend.py†L22-L27】 |
| POST | /spend/merchants | `spend.create_merchant` | API key | n/a | `MerchantCreate` | `MerchantRead` | 201【F:app/routers/spend.py†L30-L32】 |
| POST | /spend/allow | `spend.allow_usage` | API key | n/a | `AllowedUsageCreate` | status dict | 201/200 |【F:app/routers/spend.py†L35-L37】 |
| POST | /spend/purchases | `spend.create_purchase` | API key | n/a | `PurchaseCreate` + Idempotency-Key | `PurchaseRead` | 201【F:app/routers/spend.py†L40-L46】 |
| POST | /spend/allowed | `spend.add_allowed_payee` | API key | n/a | Inline `AddPayeeIn` | Dict summary | 201【F:app/routers/spend.py†L49-L74】 |
| POST | /spend | `spend.spend` | API key | n/a | Inline `SpendIn` + Idempotency-Key | Dict summary | 200【F:app/routers/spend.py†L77-L105】 |
| POST | /proofs | `proofs.submit_proof` | API key | n/a | `ProofCreate` | `ProofRead` | 201【F:app/routers/proofs.py†L11-L18】 |
| POST | /proofs/{id}/decision | `proofs.decide_proof` | API key | n/a | `ProofDecision` | `ProofRead` | 200/400 |【F:app/routers/proofs.py†L21-L33】 |
| POST | /payments/execute/{payment_id} | `payments.execute_payment` | API key | n/a | Path ID | `PaymentRead` | 200/404/409 |【F:app/routers/payments.py†L10-L17】 |
| POST | /psp/webhook | `psp.psp_webhook` | None | n/a | Raw JSON + headers | Ack dict | 200/401 |【F:app/routers/psp.py†L15-L45】 |

## D. Data model & states
| Entity | Key fields | Constraints / Indexes | Notes |
| --- | --- | --- | --- |
| User | `username`, `email`, `is_active` | Unique username/email; relationships for sent/received transactions | Core identity records for other tables.【F:app/models/user.py†L8-L22】 |
| Alert | `type`, `message`, `actor_user_id`, `payload_json` | Index on type + created_at | Stores security/ops events.【F:app/models/alert.py†L8-L17】 |
| CertifiedAccount | `user_id`, `level`, `certified_at` | Unique `user_id` | Tracks certification level enum.【F:app/models/certified.py†L9-L21】 |
| EscrowAgreement | Parties, `amount_total`, `status`, `deadline_at`, `release_conditions_json` | Check `amount_total >=0`, indices on status/deadline | Owns deposits, events, milestones.【F:app/models/escrow.py†L23-L43】 |
| EscrowDeposit | `escrow_id`, `amount`, `idempotency_key` | Check `amount>0`, unique idempotency | Enables idempotent funding.【F:app/models/escrow.py†L45-L55】 |
| EscrowEvent | `escrow_id`, `kind`, `data_json`, `at` | Index on escrow & idempotency_key | Timeline of status changes, spend logs.【F:app/models/escrow.py†L58-L69】 |
| Milestone | `escrow_id`, `idx`, `amount`, geofence fields, `status` | Unique `(escrow_id, idx)`, positivity/geofence checks | Drives proof validation & payouts.【F:app/models/milestone.py†L11-L47】 |
| Proof | `escrow_id`, `milestone_id`, `sha256`, `metadata_`, `status` | Unique SHA-256; indexes on escrow/milestone | Stores evidence for release decisions.【F:app/models/proof.py†L10-L24】 |
| Payment | `escrow_id`, `milestone_id`, `amount`, `psp_ref`, `status`, `idempotency_key` | Check `amount>0`; unique PSP ref & idempotency; indices on status | Represents outgoing payouts.【F:app/models/payment.py†L21-L38】 |
| Transaction | `sender_id`, `receiver_id`, `amount`, `status`, `idempotency_key` | Check `amount>0`; indices on status and parties; unique idempotency | Restricted transfers with allowlist enforcement.【F:app/models/transaction.py†L20-L37】 |
| AllowedRecipient | `owner_id`, `recipient_id` | Unique pair constraint | Allowlist for restricted transfers.【F:app/models/allowlist.py†L8-L15】 |
| AllowedPayee | `escrow_id`, `payee_ref`, limits | Unique `(escrow_id,payee_ref)`; non-negative checks | Enforces spend limits in usage module.【F:app/models/allowed_payee.py†L11-L32】 |
| SpendCategory | `code`, `label` | Unique code | Policy classification for merchants.【F:app/models/spend.py†L13-L21】 |
| Merchant | `name`, `category_id`, `is_certified` | Unique name; index on category | Accepts purchases; certification bypasses usage checks.【F:app/models/spend.py†L24-L34】 |
| AllowedUsage | `owner_id`, `merchant_id`/`category_id` | Mutual exclusivity check; unique combos | Configures spend permissions.【F:app/models/spend.py†L37-L53】 |
| Purchase | `sender_id`, `merchant_id`, `amount`, `status`, `idempotency_key` | Check `amount>0`; indexes; idempotency unique; **stored as float** | Needs Decimal fix before production.【F:app/models/spend.py†L64-L83】 |
| PSPWebhookEvent | `event_id`, `psp_ref`, `kind`, `raw_json` | Unique event_id; indexes on kind/received | Persists PSP callbacks for idempotence.【F:app/models/psp_webhook.py†L9-L21】 |
| AuditLog | `actor`, `action`, `entity`, `entity_id`, `data_json`, `at` | Primary key only | Central audit sink used by finance flows.【F:app/models/audit.py†L10-L20】 |

**State machines**
- `EscrowStatus`: DRAFT → FUNDED → RELEASABLE → RELEASED, with REFUNDED/CANCELLED as terminals.【F:app/models/escrow.py†L12-L20】 Escrow service transitions map to events but lack audits.【F:app/services/escrow.py†L121-L180】
- `MilestoneStatus`: WAITING → PENDING_REVIEW → APPROVED/REJECTED → PAYING → PAID.【F:app/models/milestone.py†L11-L19】【F:app/services/proofs.py†L172-L318】
- `PaymentStatus`: PENDING → SENT → SETTLED/ERROR/REFUNDED; idempotent retries keep state consistent.【F:app/models/payment.py†L11-L38】【F:app/services/payments.py†L84-L203】
- `TransactionStatus`: Defaults to PENDING but service commits as COMPLETED; future states reserved.【F:app/models/transaction.py†L11-L37】【F:app/services/transactions.py†L61-L86】
- `PurchaseStatus`: Always COMPLETED today; future states defined but unused.【F:app/models/spend.py†L56-L83】
- Proof records store free-form status strings (`PENDING`/`APPROVED`/`REJECTED`) controlled in service logic.【F:app/models/proof.py†L15-L22】【F:app/services/proofs.py†L172-L360】

## E. Stability results
- `alembic upgrade head` initially failed because `.env` still exposed `PSP_WEBHOOK_SECRET`, which `Settings` forbids; removing the extra key allowed the migration to succeed.【44a73b†L1-L33】【1638b0†L1-L3】
- `pytest -q` passes (21 tests, 0 failures/xfails/skip).【3f08df†L1-L2】
- No lint/static tools configured in requirements; manual review flagged blocking issues below.
- Idempotency controls exist for deposits, purchases, spends, payments, and transactions via shared helper, mitigating duplicate submissions.【F:app/services/idempotency.py†L1-L39】【F:app/services/payments.py†L84-L203】【F:app/services/usage.py†L80-L235】
- Database sessions are synchronous with per-request dependency and engine lifecycle handled in lifespan/on_event. No connection leak observed in code review.【F:app/db.py†L10-L77】【F:app/main.py†L20-L63】

## F. Security & integrity
- **Authentication/Authorization**: Entire API (except PSP webhook and health) depends on a single bearer API key; no user-level auth, scopes, or rotation support.【F:app/security.py†L7-L21】【F:app/routers/__init__.py†L10-L19】
- **PSP ingress**: Webhook lacks any dependency guard and trusts an environment variable `_SECRET` defaulting to empty string, so unsigned requests succeed unless ops set OS env separately (config isn’t validated).【F:app/routers/psp.py†L15-L45】【F:app/services/psp_webhooks.py†L20-L35】
- **Input validation**: Pydantic schemas enforce positive amounts/currency codes across escrows, transactions, and purchases, plus inline validators for spend rules.【F:app/schemas/escrow.py†L19-L43】【F:app/schemas/transaction.py†L8-L37】【F:app/schemas/spend.py†L1-L53】
- **File/proof pipeline**: Photo proofs validated for EXIF timestamps, geofence bounds, trusted sources, and age before auto-approval; errors trigger 422 responses.【F:app/services/proofs.py†L45-L170】【F:app/services/rules.py†L15-L107】
- **Audit & logging**: Most financial flows emit structured audit rows and log context; however, escrow lifecycle updates skip AuditLog entirely, violating audit policy for state-changing operations.【F:app/services/transactions.py†L73-L86】【F:app/services/payments.py†L237-L303】【F:app/services/escrow.py†L36-L190】
- **Secrets/config**: Application settings only recognise `app_env`, `database_url`, and `api_key`; PSP secret is unmanaged and absent from validation, increasing misconfiguration risk.【F:app/config.py†L7-L26】【F:app/services/psp_webhooks.py†L20-L35】
- **Rate limiting/abuse**: No throttling or abuse detection in routers, despite sensitive money-moving endpoints.【F:app/routers/__init__.py†L10-L19】

## G. Observability & ops
- Logging configured centrally with JSON formatter; lifespan ensures setup on startup with optional legacy path for backwards compatibility.【F:app/core/logging.py†L10-L31】【F:app/main.py†L20-L55】
- Error handlers wrap uncaught exceptions into structured payloads, preventing stack traces from leaking.【F:app/main.py†L66-L80】
- Database helpers lazily initialise engine/session factory, add SQLite pragmas, and provide dependency for FastAPI routes.【F:app/db.py†L10-L77】
- Migration history consists of single init revision; no drift detected after successful `upgrade head`.【F:alembic/versions/baa4932d9a29_0001_init_schema.py†L16-L199】
- Configuration relies on `.env` for minimal settings; missing PSP secret in Settings encourages ad-hoc OS env injection, which isn’t documented or validated.【F:app/config.py†L7-L26】【F:app/services/psp_webhooks.py†L20-L35】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Spend purchases | Monetary amounts stored as float (`asdecimal=False`), causing rounding drift and potential ledger imbalance. | High | High | P0 | Change ORM column and schemas to use `Decimal` everywhere, run migration to convert existing data, add regression tests.【F:app/models/spend.py†L64-L80】 |
| R2 | PSP webhook ingress | Unauthenticated webhook + empty default secret allows forged settlement/failure events. | Critical | High | P0 | Require API key or HMAC verified against validated secret from Settings; reject when secret missing; add signature tests.【F:app/routers/psp.py†L15-L45】【F:app/services/psp_webhooks.py†L20-L60】 |
| R3 | Escrow lifecycle auditing | Create/approve/reject paths mutate funds without AuditLog entries, violating audit policy. | High | Medium | P0 | Emit AuditLog records for each escrow state change alongside existing events; add tests ensuring audit coverage.【F:app/services/escrow.py†L36-L190】 |
| R4 | Startup lifecycle | Conditional `@app.on_event` path risks diverging initialisation (policy forbids legacy path). | Medium | Medium | P0 | Remove on_event fallback, rely exclusively on lifespan, and update settings/tests accordingly.【F:app/main.py†L36-L55】 |
| R5 | Authentication | Single static API key controls whole surface; no rotation or per-user auth. | High | Medium | P1 | Integrate proper user auth (JWT/OAuth) or scoped API keys, add rate limiting, document rotation.【F:app/security.py†L7-L21】 |
| R6 | PSP secret management | Secret not part of validated settings; silent empty default undermines security posture. | High | Medium | P1 | Add `psp_webhook_secret` to `Settings`, fail fast when missing, document `.env` usage.【F:app/config.py†L7-L26】【F:app/services/psp_webhooks.py†L20-L35】 |
| R7 | Rate limiting | No throttling on money-moving endpoints → brute-force/idempotency key abuse possible. | Medium | Medium | P2 | Introduce rate limiting middleware or gateway rules per API key.【F:app/routers/__init__.py†L10-L19】 |

## I. Roadmap to MVP-ready
- **P0**
  - Fix spend float storage → migrate to Decimal with lossless conversion.【F:app/models/spend.py†L64-L80】
  - Secure PSP webhook: require configured secret, validate signature, and add auth dependency.【F:app/routers/psp.py†L15-L45】【F:app/services/psp_webhooks.py†L20-L60】
  - Add AuditLog coverage for escrow lifecycle operations and remove legacy `@app.on_event` fallback.【F:app/services/escrow.py†L36-L190】【F:app/main.py†L36-L55】
- **P1**
  - Expand settings to cover PSP secret & other sensitive config with validation/documentation.【F:app/config.py†L7-L26】
  - Replace global API key with scoped credentials or JWT auth, plus rotation tooling.【F:app/security.py†L7-L21】
- **P2**
  - Implement rate limiting / abuse detection at router or infrastructure layer.【F:app/routers/__init__.py†L10-L19】
  - Extend monitoring (structured logs already JSON) with metrics/tracing integration.

**Verdict: Not yet safe to expose to real users until P0 items are resolved.**
