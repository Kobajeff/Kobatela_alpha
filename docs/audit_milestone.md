# Audit – Escrow Milestones & Proof-Based Release

## 1. Overview
- The codebase supports multi-milestone escrows with sequencing and per-milestone proof + payout wiring, but enforcement of total/ordering rules relies mostly on runtime checks in the proof service and tests rather than database constraints.
- Proof submission is the entry point for milestone progression; photo proofs can auto-approve and trigger payouts when geofence/EXIF checks pass, while document proofs stay manual but feed OCR and AI advisory context.
- Sender-provided expectations exist as JSON (`release_conditions_json`, `proof_requirements`) and usage mandates, yet only geofence and limited invoice fields are actively enforced; other expectations are passed to AI or stored without blocking logic.
- Payments are linked to milestones via `milestone_id`, executed idempotently, and can update escrow status to RELEASED when all milestones are PAID.
- Tests exercise sequencing, geofence hard failures, soft-review paths, OCR normalization, AI persistence, and payout chaining, giving partial confidence in the flow.

## 2. Escrow & Milestone Data Model
- `EscrowAgreement` stores total amount/currency, status, domain, deadline, and free-form `release_conditions_json` but has no direct FK to milestones; milestones point back to it.【F:app/models/escrow.py†L30-L82】【F:app/models/milestone.py†L35-L62】
- `Milestone` includes `idx` (sequence), amount, proof type, validator, optional `proof_requirements`, and geofence fields; uniqueness on `(escrow_id, idx)` enforces per-escrow ordering uniqueness but not contiguity or sum checks.【F:app/models/milestone.py†L35-L62】
- `Proof` references both escrow and milestone, stores metadata plus AI/OCR fields (invoice totals, AI risk/flags), and defaults to `PENDING` status on creation unless auto-approved.【F:app/models/proof.py†L16-L51】
- `Payment` optionally links to a milestone and records amount, idempotency key, PSP reference, and status; payouts can thus be per-milestone.【F:app/models/payment.py†L21-L40】
- `UsageMandate` captures sender-side constraints (allowed merchant/category, total amount, currency, expiry) but is not wired to milestone proofs directly.【F:app/models/usage_mandate.py†L30-L66】

## 3. Milestone Lifecycle & Release
- Milestone states span `WAITING → PENDING_REVIEW/APPROVED → PAYING → PAID`, with rejection resetting status; states are stored on the model enum.【F:app/models/milestone.py†L21-L29】【F:app/models/payment.py†L11-L19】
- `submit_proof` enforces sequence by comparing the current open milestone (first non-PAID in order) and rejects submissions for future indices (`SEQUENCE_ERROR`).【F:app/services/proofs.py†L294-L318】 Tests cover this rejection path.【F:tests/test_milestone_sequence_and_exif.py†L40-L83】
- Photo proofs validate EXIF timestamp and geofence; hard violations raise 422, soft issues mark milestone `PENDING_REVIEW`. Passing validation sets `auto_approve=True`, creating a proof with status `APPROVED` and setting the milestone to `APPROVED`.【F:app/services/proofs.py†L126-L355】
- When `auto_approve` is true, `submit_proof` immediately executes a payout via `payments_service.execute_payout`, moving the milestone to `PAID` and potentially releasing the escrow when all milestones are paid.【F:app/services/proofs.py†L417-L454】【F:app/services/payments.py†L193-L274】
- Manual approvals use `/proofs/{id}/decision`, which routes to `approve_proof`/`reject_proof`; approval triggers payout with an idempotency key per milestone amount and then finalizes escrow state if all milestones are paid.【F:app/routers/proofs.py†L18-L41】【F:app/services/proofs.py†L458-L520】【F:app/services/payments.py†L193-L274】【F:app/services/payments.py†L330-L373】
- Tests confirm auto-approve payouts and escrow release after single milestone payment, as well as idempotent payout reuse and error reuse rejection paths.【F:tests/test_auto_approve_and_payout.py†L34-L117】【F:tests/test_auto_approve_and_payout.py†L119-L201】

## 4. Sender-Defined Conditions & Expected Data
- Escrow creation accepts `release_conditions` JSON stored verbatim in `release_conditions_json`, but no downstream enforcement is visible in proof or payment services.【F:app/services/escrow.py†L62-L105】【F:app/models/escrow.py†L30-L55】
- Milestones carry `proof_requirements` JSON and geofence fields; geofence is enforced for PHOTO proofs, while `proof_requirements` inform AI context and document backend checks but do not hard-block approvals beyond amount/currency/date/supplier comparisons in advisory checks.【F:app/models/milestone.py†L53-L60】【F:app/services/document_checks.py†L17-L103】【F:app/services/proofs.py†L245-L290】
- Usage mandates define allowed merchant/category and amount caps but are not consulted in the proof submission path; they likely apply to spend flows rather than milestone payouts.【F:app/models/usage_mandate.py†L30-L66】
- Customization supported today: geofence + EXIF for PHOTO, expected invoice amount/currency/date/supplier/IBAN last4 via `proof_requirements` feeding `compute_document_backend_checks`. Missing: enforced sum of milestones to escrow amount, mandatory proof types per escrow, or dynamic rule evaluation beyond photo geofence.

## 5. Proof Verification Pipeline
- Endpoint `/proofs` (sender scope) accepts `ProofCreate`, masks metadata in responses, and delegates to `submit_proof`. Decisions occur at `/proofs/{id}/decision` for support/admin scopes.【F:app/routers/proofs.py†L18-L41】
- For PDF/INVOICE/CONTRACT proofs, OCR is invoked via `run_invoice_ocr_if_enabled`, normalizing invoice total and currency; normalization errors yield 422. Metadata retains OCR raw output and normalized fields.【F:app/services/proofs.py†L87-L123】【F:app/services/proofs.py†L329-L354】
- `compute_document_backend_checks` compares expected amount/currency/date/supplier/IBAN last4 from `proof_requirements` against metadata and feeds results to AI; it does not block submissions by itself.【F:app/services/document_checks.py†L17-L103】
- Photo validation leverages `rules_service.validate_photo_metadata` plus Haversine geofence enforcement; hard errors (geofence/time/EXIF) raise 422, while untrusted sources create review-required proofs.【F:app/services/proofs.py†L126-L198】 Tests assert both failure and review flows.【F:tests/test_milestone_sequence_and_exif.py†L85-L170】
- AI Proof Advisor is optional; on success its output is stored in proof metadata and AI columns, but exceptions are logged and do not block submission. Manual approval requires a note if AI flagged warning/suspect.【F:app/services/proofs.py†L201-L287】【F:app/services/proofs.py†L458-L513】
- Approved proofs trigger payouts tied to milestones; payments mark milestones `PAID` and may close the escrow via `_finalize_escrow_if_paid`. Tests show proof approval leading to payment status `SENT` and escrow status `RELEASED`.【F:app/services/payments.py†L193-L274】【F:tests/test_proof_payment_flow.py†L65-L154】

## 6. Gaps, Limitations & Recommendations
- No database or service check ensures the sum of milestone amounts equals `EscrowAgreement.amount_total`, allowing over/under-allocation; add validation on milestone creation and a DB constraint or service-level check.【F:app/models/escrow.py†L40-L52】【F:app/models/milestone.py†L35-L60】
- Milestone sequencing relies on runtime lookup of the first open milestone; there is no guarantee milestones are contiguous or that earlier milestones are funded before creation—consider enforcing contiguous `idx` and optional “open only when previous paid” flags at creation time.【F:app/services/proofs.py†L294-L327】
- `release_conditions_json` and `usage_mandate` rules are unused in proof validation/payout decisions; wiring them into `rules_service` or backend checks would allow sender-defined conditions to influence approvals.【F:app/services/escrow.py†L62-L105】【F:app/models/usage_mandate.py†L30-L66】
- Document proof requirements are advisory only; to prevent incorrect payouts, elevate `compute_document_backend_checks` results into blocking logic or workflow states (e.g., require manual review when amount/currency mismatch).【F:app/services/document_checks.py†L17-L103】【F:app/services/proofs.py†L245-L291】
- Geofence fields use `Float` without precision handling, and `proof_requirements` is duplicated in the model; consider consolidating the column and using `Numeric` for coordinates if accuracy is critical.【F:app/models/milestone.py†L35-L60】
- PSP webhook handling and settlement flows exist but are out of scope for this audit; ensure signature verification and mapping to milestone payments are covered elsewhere.

