# Kobatela_alpha — Capability & Stability Audit (2025-11-13)

## A. Executive summary
- Forces :
  - RBAC désormais explicite : toutes les routes sensibles s’appuient sur `require_scope` avec ensembles de scopes (`admin`, `support`, `sender`) et audit des usages de clés, y compris la clé legacy confinée au mode dev.【F:app/routers/transactions.py†L23-L59】【F:app/routers/users.py†L12-L35】【F:app/security.py†L31-L149】
  - Les mutations antifraude (allowlist, certification, transactions restreintes) sont idempotentes et journalisées dans `AuditLog`, préservant un historique complet des décisions.【F:app/services/transactions.py†L46-L182】
  - Toutes les sommes critiques reposent sur `Numeric(18,2)` avec conversions `Decimal`, évitant toute dérive flottante pour escrows, paiements, achats ou mandats.【F:app/models/escrow.py†L19-L55】【F:app/models/payment.py†L21-L37】【F:app/models/spend.py†L61-L83】【F:app/models/usage_mandate.py†L39-L64】
  - Le pipeline PSP applique une signature HMAC + horodatage, refuse l’absence de secret et persist e chaque événement pour idempotence et audit.【F:app/routers/psp.py†L20-L61】【F:app/services/psp_webhooks.py†L14-L87】
  - Le lifecycle escrow/milestone déclenche audits et événements cohérents (création, dépôts, livraisons, paiements) avec clôture automatique lorsqu’un paiement manuel termine tous les jalons.【F:app/services/escrow.py†L60-L248】【F:app/services/payments.py†L206-L333】
- Risques :
  - Plusieurs endpoints mutateurs (`POST /users`, `/spend/categories`, `/spend/merchants`, `/spend/allow`) ne produisent aucun `AuditLog`, ce qui viole la traçabilité exigée (P0 selon la règle interne).【F:app/routers/users.py†L15-L28】【F:app/services/spend.py†L97-L184】
  - L’auto-génération d’`Idempotency-Key` sur `POST /spend` laisse les clients sans protection contre les doubles envois réseau : deux retries sans header créent des paiements distincts (risque financier P1).【F:app/routers/spend.py†L115-L140】
  - Aucun audit ni garde spécifique n’existe sur la création d’utilisateurs support ; un compte `support` peut créer des comptes sans piste dédiée (P1 conformité).【F:app/routers/users.py†L15-L31】
  - Les créations de catégories/merchants ne contrôlent pas l’acteur (scope `sender` autorisé) et ne journalisent pas l’origine, ouvrant une surface d’abus catalogues (P1).【F:app/routers/spend.py†L33-L59】【F:app/services/spend.py†L97-L184】
  - Le scheduler APScheduler reste en mémoire sans verrou distribué ; mal configuré, plusieurs réplicas pourraient exécuter `expire_mandates` en double (P2).【F:app/main.py†L23-L64】

Readiness score : **74 / 100** — GO conditionnel (corriger l’audit manquant avant exposition à des données sensibles).

## B. Capability map (current, concrete)
### B.1 Feature coverage
| Feature | Implemented endpoints/modules | Status | Notes |
| --- | --- | --- | --- |
| Santé & métadonnées | `GET /health` → `health.healthcheck` | Implémenté | Ping JSON sans auth pour monitoring.【F:app/routers/health.py†L4-L11】 |
| Gestion clés API | `POST/GET/DELETE /apikeys` | Implémenté | Restreint à `admin`, génération + audit création/révocation.【F:app/routers/apikeys.py†L62-L173】 |
| Gestion utilisateurs | `POST/GET /users` | Partiel (Audit manquant) | RBAC `admin/support`, mais aucune trace d’audit sur création/lecture.【F:app/routers/users.py†L12-L41】 |
| Allowlist & certification | `POST /allowlist`, `POST /certified` | Implémenté | Admin-only, déduplication et audit détaillé.【F:app/routers/transactions.py†L23-L42】【F:app/services/transactions.py†L46-L105】 |
| Transactions restreintes | `POST/GET /transactions` | Implémenté | Idempotence, alerting antifraude et audit complet.【F:app/routers/transactions.py†L45-L76】【F:app/services/transactions.py†L110-L182】 |
| Escrow lifecycle | `/escrows/*` | Implémenté | Création, dépôts idempotents, transitions client/provider, audit systématique.【F:app/routers/escrow.py†L13-L67】【F:app/services/escrow.py†L60-L248】 |
| Mandats d’usage | `/mandates`, `/mandates/cleanup` | Implémenté | Validation bénéficiaires/merchants + audit création, cron piloté par scheduler.【F:app/routers/mandates.py†L13-L32】【F:app/services/mandates.py†L16-L109】 |
| Catalogue spend | `/spend/categories`, `/spend/merchants` | Partiel (Audit manquant) | Anti-doublon SQL mais aucun `AuditLog`; scope `sender` autorisé.【F:app/routers/spend.py†L33-L52】【F:app/services/spend.py†L97-L139】 |
| Allow usage | `POST /spend/allow` | Partiel (Audit manquant) | Configure règles allowlist locales sans traçabilité acteur.【F:app/routers/spend.py†L53-L59】【F:app/services/spend.py†L142-L184】 |
| Purchases conditionnels | `POST /spend/purchases` | Implémenté | Consommation mandat atomique, audit `CREATE_PURCHASE`.【F:app/routers/spend.py†L62-L74】【F:app/services/spend.py†L187-L341】 |
| Allowed payees & spend | `POST /spend/allowed`, `POST /spend` | Implémenté | Ajout payee audité, dépenses idempotentes avec verrou pessimiste.【F:app/routers/spend.py†L76-L140】【F:app/services/usage.py†L23-L246】 |
| Proof pipeline | `POST /proofs`, `POST /proofs/{id}/decision` | Implémenté | Validation EXIF/geofence, auto-approval et audits.【F:app/routers/proofs.py†L12-L37】【F:app/services/proofs.py†L63-L214】 |
| Paiements & PSP | `POST /payments/execute/{id}`, `POST /psp/webhook` | Implémenté | Exécution idempotente, audit `EXECUTE_PAYOUT`, HMAC PSP, clôture escrow automatique.【F:app/routers/payments.py†L11-L22】【F:app/services/payments.py†L206-L333】【F:app/routers/psp.py†L20-L61】 |
| Back-office alerting | `GET /alerts` | Implémenté | Lecture filtrable réservée aux scopes `admin/support`.【F:app/routers/alerts.py†L12-L25】 |

### B.2 Supported end-to-end flows (today)
- Mandat diaspora → achat conditionnel : `/users` (création bénéficiaire) → `/mandates` (validation+audit) → `/spend/purchases` (consommation mandat + audit).【F:app/routers/users.py†L12-L35】【F:app/services/mandates.py†L68-L109】【F:app/services/spend.py†L187-L341】
- Escrow avec preuve photo : `/escrows` → `/escrows/{id}/deposit` (idempotent) → `/proofs` (validation EXIF/GPS) → paiement automatique + clôture `CLOSED` via `_finalize_escrow_if_paid`.【F:app/routers/escrow.py†L13-L63】【F:app/services/escrow.py†L60-L248】【F:app/services/payments.py†L206-L333】
- Paiement manuel + webhook PSP : `/payments/execute/{id}` (audit + event) → `/psp/webhook` (HMAC/timestamp, idempotence) → statut `SETTLED/FAILED` mis à jour avec audit.【F:app/services/payments.py†L206-L283】【F:app/routers/psp.py†L20-L61】【F:app/services/psp_webhooks.py†L38-L87】

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request | Response | Codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | /health | `health.healthcheck` | Aucune | - | - | `{status}` | 200【F:app/routers/health.py†L4-L11】 |
| POST | /users | `users.create_user` | API key + scope | `admin`, `support` | `UserCreate` | `UserRead` | 201/400 |【F:app/routers/users.py†L12-L28】|
| GET | /users/{id} | `users.get_user` | API key + scope | `admin`, `support` | - | `UserRead` | 200/404 |【F:app/routers/users.py†L31-L41】|
| POST | /allowlist | `transactions.add_to_allowlist` | API key + scope | `admin` | `AllowlistCreate` | `{status}` | 201 |【F:app/routers/transactions.py†L23-L31】|
| POST | /certified | `transactions.add_certification` | API key + scope | `admin` | `CertificationCreate` | `{status}` | 201 |【F:app/routers/transactions.py†L34-L42】|
| POST | /transactions | `transactions.post_transaction` | API key + scope | `sender`, `admin` | `TransactionCreate` + header optionnel | `TransactionRead` | 201 |【F:app/routers/transactions.py†L45-L59】|
| GET | /transactions/{id} | `transactions.get_transaction` | API key | Tous scopes | - | `TransactionRead` | 200/404 |【F:app/routers/transactions.py†L62-L76】|
| POST | /escrows | `escrow.create_escrow` | API key + scope | `sender`, `admin` | `EscrowCreate` | `EscrowRead` | 201 |【F:app/routers/escrow.py†L13-L22】|
| POST | /escrows/{id}/deposit | `escrow.deposit` | API key + scope | `sender`, `admin` | `EscrowDepositCreate` + header optionnel | `EscrowRead` | 200 |【F:app/routers/escrow.py†L25-L32】|
| POST | /escrows/{id}/mark-delivered | `escrow.mark_delivered` | API key + scope | `sender`, `admin` | `EscrowActionPayload` | `EscrowRead` | 200 |【F:app/routers/escrow.py†L35-L37】|
| POST | /escrows/{id}/client-approve | `escrow.client_approve` | API key + scope | `sender`, `admin` | `EscrowActionPayload?` | `EscrowRead` | 200 |【F:app/routers/escrow.py†L40-L46】|
| POST | /escrows/{id}/client-reject | `escrow.client_reject` | API key + scope | `sender`, `admin` | `EscrowActionPayload?` | `EscrowRead` | 200 |【F:app/routers/escrow.py†L49-L55】|
| POST | /escrows/{id}/check-deadline | `escrow.check_deadline` | API key + scope | `sender`, `admin` | - | `EscrowRead` | 200 |【F:app/routers/escrow.py†L58-L60】|
| GET | /escrows/{id} | `escrow.read_escrow` | API key + scope | `sender`, `admin` | - | `EscrowRead` | 200/404 |【F:app/routers/escrow.py†L63-L68】|
| GET | /alerts | `alerts.list_alerts` | API key + scope | `admin`, `support` | Query `type?` | `list[AlertRead]` | 200 |【F:app/routers/alerts.py†L12-L25】|
| POST | /mandates | `mandates.create_mandate` | API key + scope | `sender`, `admin` | `UsageMandateCreate` | `UsageMandateRead` | 201 |【F:app/routers/mandates.py†L13-L24】|
| POST | /mandates/cleanup | `mandates.cleanup_expired_mandates` | API key + scope | `sender`, `admin` | - | `{expired}` | 202 |【F:app/routers/mandates.py†L27-L32】|
| POST | /spend/categories | `spend.create_category` | API key + scope | `sender`, `admin` | `SpendCategoryCreate` | `SpendCategoryRead` | 201 |【F:app/routers/spend.py†L33-L40】|
| POST | /spend/merchants | `spend.create_merchant` | API key + scope | `sender`, `admin` | `MerchantCreate` | `MerchantRead` | 201 |【F:app/routers/spend.py†L43-L50】|
| POST | /spend/allow | `spend.allow_usage` | API key + scope | `sender`, `admin` | `AllowedUsageCreate` | `{status}` | 201/200 |【F:app/routers/spend.py†L53-L59】|
| POST | /spend/purchases | `spend.create_purchase` | API key + scope | `sender`, `admin` | `PurchaseCreate` + header optionnel | `PurchaseRead` | 201 |【F:app/routers/spend.py†L62-L74】|
| POST | /spend/allowed | `spend.add_allowed_payee` | API key + scope | `sender`, `admin` | `AddPayeeIn` | Dict payee | 201 |【F:app/routers/spend.py†L84-L105】|
| POST | /spend | `spend.spend` | API key + scope | `sender`, `admin` | `SpendIn` + header optionnel | Dict paiement | 200 |【F:app/routers/spend.py†L115-L140】|
| POST | /payments/execute/{id} | `payments.execute_payment` | API key + scope | `sender`, `admin` | - | `PaymentRead` | 200/404 |【F:app/routers/payments.py†L11-L22】|
| POST | /proofs | `proofs.submit_proof` | API key + scope | `sender`, `admin` | `ProofCreate` | `ProofRead` | 201/404 |【F:app/routers/proofs.py†L12-L23】|
| POST | /proofs/{id}/decision | `proofs.decide_proof` | API key + scope | `sender`, `admin` | `ProofDecision` | `ProofRead` | 200/400 |【F:app/routers/proofs.py†L26-L37】|
| POST | /psp/webhook | `psp.psp_webhook` | Secret PSP + signature | Service PSP | JSON | `{ok,event_id}` | 200/401/503 |【F:app/routers/psp.py†L20-L61】|
| POST | /apikeys | `apikeys.create_api_key` | API key + scope | `admin` | `CreateKeyIn` | `ApiKeyCreateOut` | 201/400 |【F:app/routers/apikeys.py†L62-L113】|
| GET | /apikeys/{id} | `apikeys.get_apikey` | API key + scope | `admin` | - | `ApiKeyRead` | 200/404 |【F:app/routers/apikeys.py†L116-L128】|
| DELETE | /apikeys/{id} | `apikeys.revoke_apikey` | API key + scope | `admin` | - | Vide | 204/404 |【F:app/routers/apikeys.py†L131-L173】|

## D. Data model & states
| Entity | Key fields & contraintes | Notes |
| --- | --- | --- |
| User | `username`, `email` uniques, `is_active` | Relations vers transactions envoyées/reçues (cascade).【F:app/models/user.py†L9-L21】 |
| ApiKey | `prefix`, `key_hash`, `scope`, `is_active`, `expires_at` | Enum `ApiScope`, audit de chaque usage dans `require_api_key`.【F:app/models/api_key.py†L12-L31】【F:app/security.py†L113-L127】 |
| AuditLog | `actor`, `action`, `entity`, `entity_id`, `data_json`, `at` | Base d’audit centralisée horodatée.【F:app/models/audit.py†L10-L20】 |
| AllowedRecipient | `owner_id`, `recipient_id` (unique) | Gère les allowlists antifraude.【F:app/models/allowlist.py†L7-L13】 |
| CertifiedAccount | `user_id` unique, `level`, `certified_at` | Enum `CertificationLevel`, audit lors des mises à jour.【F:app/models/certified.py†L16-L23】【F:app/services/transactions.py†L79-L107】 |
| Transaction | `sender_id`, `receiver_id`, `amount`, `status`, `idempotency_key` | `Numeric(18,2)`, alert en cas de destinataire non autorisé.【F:app/models/transaction.py†L20-L37】【F:app/services/transactions.py†L119-L144】 |
| EscrowAgreement | `client_id`, `provider_id`, `amount_total`, `status`, `deadline_at` | Événements JSON et audit sur chaque transition.【F:app/models/escrow.py†L19-L55】【F:app/services/escrow.py†L60-L248】 |
| EscrowDeposit | `escrow_id`, `amount`, `idempotency_key` unique | Idempotence via helper + audit `ESCROW_DEPOSITED`.【F:app/models/escrow.py†L45-L55】【F:app/services/escrow.py†L101-L173】 |
| EscrowEvent | `escrow_id`, `kind`, `data_json`, `at`, `idempotency_key?` | Timeline structurée des actions escrow.【F:app/models/escrow.py†L58-L69】 |
| Milestone | `escrow_id`, `idx`, `amount`, `status`, geofence | `Numeric(18,2)`, geofence en float, statut aligné sur preuves/paiements.【F:app/models/milestone.py†L9-L44】 |
| Proof | `escrow_id`, `milestone_id`, `sha256`, `status`, `metadata` | `sha256` unique, audit `SUBMIT_PROOF`.【F:app/models/proof.py†L8-L19】【F:app/services/proofs.py†L139-L214】 |
| Payment | `escrow_id`, `amount`, `status`, `psp_ref`, `idempotency_key` | `Numeric(18,2)`, audit `EXECUTE_PAYOUT`, clôture escrow auto.【F:app/models/payment.py†L18-L35】【F:app/services/payments.py†L206-L333】 |
| PSPWebhookEvent | `event_id` unique, `kind`, `psp_ref`, `raw_json`, `processed_at` | Assure idempotence et suivi settlement/erreur.【F:app/models/psp_webhook.py†L10-L25】【F:app/services/psp_webhooks.py†L54-L87】 |
| UsageMandate | `sender_id`, `beneficiary_id`, `total_amount`, `status`, `total_spent` | `Numeric(18,2)`, audit `MANDATE_CREATED`, close expirations.【F:app/models/usage_mandate.py†L30-L65】【F:app/services/mandates.py†L68-L109】 |
| AllowedPayee | `escrow_id`, `payee_ref`, limites `daily/total`, `spent_today/total` | `Numeric(18,2)`, verrou pessimiste + audit sur spend.【F:app/models/allowed_payee.py†L11-L32】【F:app/services/usage.py†L23-L245】 |
| SpendCategory & Merchant | `code`/`name` uniques, `category_id`, `is_certified` | Pas de traçabilité lors de la création (à corriger).【F:app/models/spend.py†L9-L35】【F:app/services/spend.py†L97-L139】 |

State machines :
- Escrow : `DRAFT` → `FUNDED` → `RELEASABLE` → `RELEASED/REFUNDED/CANCELLED`, orchestré par événements et audits.【F:app/models/escrow.py†L9-L55】【F:app/services/escrow.py†L168-L248】
- Milestone : `WAITING` → `PENDING_REVIEW/APPROVED` → `PAYING` → `PAID`/`REJECTED`, piloté par preuves et paiements.【F:app/models/milestone.py†L9-L44】【F:app/services/proofs.py†L172-L320】
- Payment : `PENDING` → `SENT` → `SETTLED`/`ERROR`, via `execute_payout` et webhooks PSP.【F:app/models/payment.py†L11-L35】【F:app/services/psp_webhooks.py†L38-L87】
- UsageMandate : `ACTIVE` → `CONSUMED`/`EXPIRED`, consommation atomique + cron.【F:app/models/usage_mandate.py†L22-L65】【F:app/services/spend.py†L287-L341】【F:app/services/mandates.py†L112-L176】

## E. Stability results
- `alembic upgrade head` appliqué sans erreur (chaîne linéaire jusqu’à `8b7e_add_api_keys`).【1ca5f2†L1-L12】
- `alembic current` et `alembic heads` confirment l’absence de drift (head unique).【46d6fa†L1-L4】【f1893a†L1-L3】
- `pytest -q` : 45 tests verts (1 avertissement Pydantic V2).【ec43a1†L1-L10】
- Commande `rg -n "Numeric(18, 2" app/models` a échoué (regex non fermé) avant correction, journalisée pour traçabilité.【f72ca7†L1-L5】
- Revue statique : RBAC correct sur transactions/users/alerts, HMAC PSP opérationnel, mais absence d’audit sur certaines mutations back-office et idempotence facultative côté spend.

## F. Security & integrity
- AuthN/Z : `require_api_key` audite chaque appel, désactive la clé legacy hors dev/local et `require_scope` accepte un `set[ApiScope]` avec bypass admin explicite.【F:app/security.py†L31-L149】
- Entrées Pydantic : montants positifs, devise, validation mandat/usage/proofs limitent l’injection SQL ou valeurs aberrantes.【F:app/schemas/spend.py†L12-L105】【F:app/schemas/mandates.py†L12-L57】【F:app/schemas/proof.py†L7-L33】
- Idempotence généralisée : dépôts escrow, transactions, paiements, webhooks et dépenses usage reposent sur `get_existing_by_key` et vérifications uniques.【F:app/services/idempotency.py†L9-L44】【F:app/services/escrow.py†L101-L173】【F:app/services/payments.py†L84-L283】【F:app/services/usage.py†L97-L205】
- PSP : signature HMAC SHA-256 + contrôle de dérive temporelle ±5 min, secret obligatoire au démarrage (lifespan).【F:app/main.py†L23-L52】【F:app/services/psp_webhooks.py†L14-L87】
- Audit : allowlist, certification, dépenses usage, transactions, paiements, escrow et proofs écrivent dans `AuditLog`; exceptions notables : `/users` et `/spend` catalogue sans trace (P0).【F:app/services/transactions.py†L46-L182】【F:app/services/usage.py†L23-L246】【F:app/services/payments.py†L206-L333】【F:app/services/spend.py†L97-L184】

## G. Observability & ops
- Logging structuré (`setup_logging`), CORS centralisé, Prometheus (`/metrics`) et Sentry activables par configuration.【F:app/main.py†L52-L78】【F:app/core/logging.py†L10-L31】【F:app/config.py†L32-L71】
- Lifespan FastAPI obligatoire (aucun `@app.on_event` détecté) et secret PSP vérifié avant exposition.【F:app/main.py†L23-L52】【6c65eb†L1-L1】
- Scheduler APScheduler optionnel via `SCHEDULER_ENABLED`, commentaire avertissant d’un seul runner mais pas de verrou distribué natif.【F:app/main.py†L33-L45】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| P0-1 | Audit trail | `/users`, `/spend/categories`, `/spend/merchants`, `/spend/allow` modifient des données sans `AuditLog`, rendant les investigations impossibles (exigence interne « fail hard »). | Critique | Moyenne | P0 | Ajouter un helper d’audit pour ces services et consigner l’acteur (scope, clé).【F:app/routers/users.py†L12-L28】【F:app/services/spend.py†L97-L184】 |
| P1-1 | Idempotence spend | Auto-génération d’`Idempotency-Key` crée une nouvelle clé à chaque retry sans header → double débit possible si le client attend l’idempotence implicite. | Élevé | Moyenne | P1 | Exiger un header côté client (400 sinon) ou inclure un invariant (hash payload + timestamp signé).【F:app/routers/spend.py†L115-L140】 |
| P1-2 | Back-office user management | Création d’utilisateurs support/admin sans audit ni journal dédié, difficile à tracer pour conformité. | Élevé | Faible | P1 | Introduire un audit `CREATE_USER` avec acteur + payload minimal, et envisager un scope distinct pour la création. 【F:app/routers/users.py†L15-L28】 |
| P1-3 | Catalogue spend | Endpoints catalogue accessibles aux scopes `sender` et sans audit, permettant à un client d’injecter un merchant/catégorie arbitraire. | Moyen | Moyenne | P1 | Restreindre aux scopes `admin/support` + audit creation/update. 【F:app/routers/spend.py†L33-L59】【F:app/services/spend.py†L97-L184】 |
| P2-1 | Scheduler | APScheduler en mémoire peut tourner sur plusieurs instances si `SCHEDULER_ENABLED` mal configuré. | Moyen | Faible | P2 | Documenter un seul runner obligatoire ou migrer vers un job store partagé/lock Redis. 【F:app/main.py†L33-L45】 |

## I. Roadmap to MVP-ready
- P0 :
  - Ajouter un audit obligatoire pour toute mutation user/spend catalogue (helper commun) et vérifier via test AnyIO que l’entrée `AuditLog` est créée.【F:app/services/spend.py†L97-L184】【F:app/routers/users.py†L15-L28】
- P1 :
  - Rendre `Idempotency-Key` obligatoire sur `POST /spend` (ou dériver une clé déterministe) et couvrir les retries réseau dans les tests.【F:app/routers/spend.py†L115-L140】
  - Limiter les endpoints catalogue aux scopes back-office et ajouter des tests négatifs `sender` (403).【F:app/routers/spend.py†L33-L59】
  - Journaliser les créations d’utilisateurs/support avec un audit structuré et vérifier la présence via test base de données.【F:app/routers/users.py†L15-L28】
- P2 :
  - Centraliser la configuration scheduler (un runner) et envisager un job store partagé pour éviter les doubles exécutions.【F:app/main.py†L33-L45】
  - Documenter la rotation du secret PSP et ajouter un healthcheck dédié (signature de test).【F:app/routers/psp.py†L20-L61】

**Verdict : GO conditionnel** — valider l’audit des mutations back-office avant exposition à des données sensibles.

## Evidence
- `alembic upgrade head`【1ca5f2†L1-L12】
- `alembic current`【46d6fa†L1-L4】
- `alembic heads`【f1893a†L1-L3】
- `pytest -q`【ec43a1†L1-L10】
- `rg -n "Numeric\(18, 2" app/models` (succès)【25ce01†L1-L19】
- `rg -n "verify_signature" app/services/psp_webhooks.py`【9ae4df†L1-L3】
- `rg -n "ESCROW_" app/services/escrow.py`【7d58dc†L1-L8】
- `rg -n "@app.on_event" -g"*.py"`【6c65eb†L1-L1】
- Commande échouée : `rg -n "Numeric(18, 2" app/models` (regex non fermé)【f72ca7†L1-L5】
