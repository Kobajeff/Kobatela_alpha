# Kobatela_alpha — Capability & Stability Audit (2025-11-13)

## A. Executive summary
- Forces :
  - Traçabilité centralisée : `log_audit` est appelé par les créations d’utilisateurs, le catalogue spend et les opérations antifraude, garantissant un AuditLog systématique pour chaque mutation sensible.【F:app/utils/audit.py†L10-L30】【F:app/routers/users.py†L37-L47】【F:app/services/spend.py†L112-L224】【F:app/services/transactions.py†L46-L182】
  - RBAC homogène : toutes les routes critiques reposent sur `require_scope` avec ensembles explicites et l’API spend impose désormais `Idempotency-Key` obligatoire côté client.【F:app/routers/spend.py†L33-L140】【F:app/security.py†L31-L149】
  - Sécurité financière : les montants d’escrow, paiements, achats et mandats utilisent `Numeric(18, 2)` ou `Decimal`, éliminant les dérives flottantes.【F:app/models/escrow.py†L33-L55】【F:app/models/payment.py†L21-L38】【F:app/models/spend.py†L64-L80】【F:app/models/usage_mandate.py†L46-L65】
  - Chaîne PSP durcie : la startup échoue sans secret, la signature HMAC+timestamp est vérifiée et chaque événement PSP est persisté pour idempotence.【F:app/main.py†L23-L64】【F:app/routers/psp.py†L20-L61】【F:app/services/psp_webhooks.py†L14-L87】
  - Spend conditionnel robuste : verrou pessimiste, idempotence et audits couvrent `AllowedPayee` et `USAGE_SPEND`, limitant les courses et doublons.【F:app/services/usage.py†L80-L246】
- Risques :
  - L’endpoint `/spend/allowed` ne vérifie pas que l’appelant possède l’escrow ; tout scope `sender` connaissant l’identifiant peut ajouter un bénéficiaire et contourner les limites (P0).【F:app/routers/spend.py†L84-L105】【F:app/services/usage.py†L23-L77】
  - Les audits back-office enregistrent l’acteur comme chaîne générique (`"admin"` ou `"system"`), sans rattacher la clé API réelle, ce qui fragilise les enquêtes (P1 conformité).【F:app/routers/users.py†L37-L44】【F:app/services/spend.py†L112-L224】【F:app/services/transactions.py†L59-L107】
  - Lorsqu’un `POST /spend/allow` rencontre un doublon, l’absence d’AuditLog et de métrique empêche de détecter les tentatives répétées ou malveillantes (P1).【F:app/services/spend.py†L198-L226】
  - APScheduler reste en mémoire sans verrou distribué ; une mauvaise configuration multi-pod peut déclencher `expire_mandates` en double (P2).【F:app/main.py†L33-L45】
  - Le header `Idempotency-Key` reste facultatif sur `POST /transactions`, ouvrant la porte à des virements dupliqués si le client oublie le header (P1).【F:app/routers/transactions.py†L45-L59】【F:app/services/transactions.py†L110-L182】

Readiness score : **83 / 100** — GO conditionnel (lever R1 avant données multi-locataires).

## B. Capability map (current, concrete)
### B.1 Feature coverage
| Feature | Implemented endpoints/modules | Status | Notes |
| --- | --- | --- | --- |
| Santé & métadonnées | `GET /health` → `health.healthcheck` | Implémenté | Ping JSON sans auth pour monitoring.【F:app/routers/health.py†L4-L11】 |
| Gestion clés API | `POST/GET/DELETE /apikeys` | Implémenté | Admin-only, génération hashée + audit création/révocation.【F:app/routers/apikeys.py†L62-L173】 |
| Gestion utilisateurs | `POST/GET /users` | Implémenté | Audit `CREATE_USER` et RBAC `admin/support` via API key.【F:app/routers/users.py†L12-L48】 |
| Allowlist & certification | `POST /allowlist`, `POST /certified` | Implémenté | Admin-only, déduplication + AuditLog détaillé.【F:app/routers/transactions.py†L23-L42】【F:app/services/transactions.py†L46-L107】 |
| Transactions restreintes | `POST/GET /transactions` | Implémenté | Idempotence optionnelle, alertes antifraude, audit création.【F:app/routers/transactions.py†L45-L76】【F:app/services/transactions.py†L110-L182】 |
| Escrow lifecycle | `/escrows/*` | Implémenté | Création, dépôts idempotents, transitions client/provider auditées.【F:app/routers/escrow.py†L13-L68】【F:app/services/escrow.py†L101-L213】 |
| Mandats d’usage | `/mandates`, `/mandates/cleanup` | Implémenté | Validation bénéficiaires/merchants, audit création/expiration.【F:app/routers/mandates.py†L13-L32】【F:app/services/mandates.py†L91-L175】 |
| Catalogue spend | `/spend/categories`, `/spend/merchants` | Implémenté | Restreint à `admin/support`, audit `SPEND_*_CREATED`, déduplication SQL.【F:app/routers/spend.py†L33-L50】【F:app/services/spend.py†L98-L166】 |
| Allow usage | `POST /spend/allow` | Implémenté | Vérifie merchant/category, audit `SPEND_ALLOW_CREATED`, retourne statut.【F:app/routers/spend.py†L53-L59】【F:app/services/spend.py†L169-L226】 |
| Purchases conditionnels | `POST /spend/purchases` | Implémenté | Consommation mandat atomique + audits mandat & achat.【F:app/routers/spend.py†L62-L74】【F:app/services/spend.py†L229-L413】 |
| Allowed payees & usage spend | `POST /spend/allowed`, `POST /spend` | Implémenté | Ajout audité, dépense idempotente + verrou `FOR UPDATE` et audit `USAGE_SPEND`.【F:app/routers/spend.py†L84-L140】【F:app/services/usage.py†L23-L246】 |
| Proof pipeline | `POST /proofs`, `POST /proofs/{id}/decision` | Implémenté | Validation, audit & transitions milestone/proof.【F:app/routers/proofs.py†L12-L37】【F:app/services/proofs.py†L139-L214】 |
| Paiements & PSP | `POST /payments/execute/{id}`, `POST /psp/webhook` | Implémenté | Paiements idempotents, audit `EXECUTE_PAYOUT`, HMAC PSP obligatoire.【F:app/routers/payments.py†L11-L22】【F:app/services/payments.py†L206-L333】【F:app/routers/psp.py†L20-L61】 |
| Back-office alerting | `GET /alerts` | Implémenté | Lecture filtrable réservée à `admin/support`.【F:app/routers/alerts.py†L12-L25】 |

### B.2 Supported end-to-end flows (today)
- Mandat diaspora → achat conditionnel : `/users` (création) → `/mandates` (activation + audit) → `/spend/purchases` (consommation mandat idempotente).【F:app/routers/users.py†L12-L48】【F:app/services/mandates.py†L91-L175】【F:app/services/spend.py†L229-L413】
- Escrow avec preuves et paiements : `/escrows` → `/escrows/{id}/deposit` (idempotent) → `/proofs` → `/payments/execute/{id}` (audit + clôture) → `_finalize_escrow_if_paid` déclenche `CLOSED` et audit.【F:app/routers/escrow.py†L13-L63】【F:app/services/escrow.py†L101-L213】【F:app/services/proofs.py†L139-L214】【F:app/services/payments.py†L206-L333】
- Flux PSP : `/psp/webhook` valide HMAC + timestamp, persiste l’événement et alimente la reprise idempotente des paiements.【F:app/routers/psp.py†L20-L61】【F:app/services/psp_webhooks.py†L14-L87】

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request | Response | Codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | /health | `health.healthcheck` | Aucune | - | - | `{status}` | 200【F:app/routers/health.py†L4-L11】 |
| POST | /users | `users.create_user` | API key + scope | `admin`, `support` | `UserCreate` | `UserRead` | 201/400【F:app/routers/users.py†L12-L47】 |
| GET | /users/{user_id} | `users.get_user` | API key + scope | `admin`, `support` | - | `UserRead` | 200/404【F:app/routers/users.py†L51-L61】 |
| POST | /allowlist | `transactions.add_to_allowlist` | API key + scope | `admin` | `AllowlistCreate` | `{status}` | 201/200【F:app/routers/transactions.py†L23-L31】 |
| POST | /certified | `transactions.add_certification` | API key + scope | `admin` | `CertificationCreate` | `{status}` | 201【F:app/routers/transactions.py†L34-L42】 |
| POST | /transactions | `transactions.post_transaction` | API key + scope | `sender`, `admin` | `TransactionCreate` + `Idempotency-Key?` | `TransactionRead` | 201【F:app/routers/transactions.py†L45-L59】 |
| GET | /transactions/{transaction_id} | `transactions.get_transaction` | API key | Tous scopes | - | `TransactionRead` | 200/404【F:app/routers/transactions.py†L62-L76】 |
| POST | /escrows | `escrow.create_escrow` | API key + scope | `sender`, `admin` | `EscrowCreate` | `EscrowRead` | 201【F:app/routers/escrow.py†L13-L22】 |
| POST | /escrows/{id}/deposit | `escrow.deposit` | API key + scope | `sender`, `admin` | `EscrowDepositCreate` + `Idempotency-Key?` | `EscrowRead` | 200【F:app/routers/escrow.py†L25-L32】 |
| POST | /escrows/{id}/mark-delivered | `escrow.mark_delivered` | API key + scope | `sender`, `admin` | `EscrowActionPayload` | `EscrowRead` | 200【F:app/routers/escrow.py†L35-L37】 |
| POST | /escrows/{id}/client-approve | `escrow.client_approve` | API key + scope | `sender`, `admin` | `EscrowActionPayload?` | `EscrowRead` | 200【F:app/routers/escrow.py†L40-L46】 |
| POST | /escrows/{id}/client-reject | `escrow.client_reject` | API key + scope | `sender`, `admin` | `EscrowActionPayload?` | `EscrowRead` | 200【F:app/routers/escrow.py†L49-L55】 |
| POST | /escrows/{id}/check-deadline | `escrow.check_deadline` | API key + scope | `sender`, `admin` | - | `EscrowRead` | 200【F:app/routers/escrow.py†L58-L60】 |
| GET | /escrows/{id} | `escrow.read_escrow` | API key + scope | `sender`, `admin` | - | `EscrowRead` | 200/404【F:app/routers/escrow.py†L63-L68】 |
| GET | /alerts | `alerts.list_alerts` | API key + scope | `admin`, `support` | Query `type?` | `list[AlertRead]` | 200【F:app/routers/alerts.py†L12-L25】 |
| POST | /mandates | `mandates.create_mandate` | API key + scope | `sender`, `admin` | `UsageMandateCreate` | `UsageMandateRead` | 201【F:app/routers/mandates.py†L13-L24】 |
| POST | /mandates/cleanup | `mandates.cleanup_expired_mandates` | API key + scope | `sender`, `admin` | - | `{expired}` | 202【F:app/routers/mandates.py†L27-L32】 |
| POST | /spend/categories | `spend.create_category` | API key + scope | `admin`, `support` | `SpendCategoryCreate` | `SpendCategoryRead` | 201【F:app/routers/spend.py†L33-L40】 |
| POST | /spend/merchants | `spend.create_merchant` | API key + scope | `admin`, `support` | `MerchantCreate` | `MerchantRead` | 201【F:app/routers/spend.py†L43-L50】 |
| POST | /spend/allow | `spend.allow_usage` | API key + scope | `admin`, `support` | `AllowedUsageCreate` | `{status}` | 201/200【F:app/routers/spend.py†L53-L59】 |
| POST | /spend/purchases | `spend.create_purchase` | API key + scope | `sender`, `admin` | `PurchaseCreate` + `Idempotency-Key?` | `PurchaseRead` | 201【F:app/routers/spend.py†L62-L74】 |
| POST | /spend/allowed | `spend.add_allowed_payee` | API key + scope | `sender`, `admin` | `AddPayeeIn` | Payee dict | 201【F:app/routers/spend.py†L84-L105】 |
| POST | /spend | `spend.spend` | API key + scope | `sender`, `admin` | `SpendIn` + `Idempotency-Key` | Paiement dict | 200/400【F:app/routers/spend.py†L115-L140】 |
| POST | /proofs | `proofs.submit_proof` | API key + scope | `sender`, `admin` | `ProofCreate` | `ProofRead` | 201【F:app/routers/proofs.py†L12-L23】 |
| POST | /proofs/{id}/decision | `proofs.decide_proof` | API key + scope | `sender`, `admin` | `ProofDecision` | `ProofRead` | 200/400【F:app/routers/proofs.py†L26-L37】 |
| POST | /payments/execute/{payment_id} | `payments.execute_payment` | API key + scope | `sender`, `admin` | - | `PaymentRead` | 200/404/409【F:app/routers/payments.py†L11-L22】 |
| POST | /psp/webhook | `psp.psp_webhook` | None (HMAC secret) | PSP | Raw JSON | `{ok,event_id}` | 200/401/503【F:app/routers/psp.py†L20-L61】 |
| POST | /apikeys | `apikeys.create_api_key` | API key + scope | `admin` | `CreateKeyIn` | `ApiKeyCreateOut` | 201/400【F:app/routers/apikeys.py†L62-L105】 |
| GET | /apikeys/{api_key_id} | `apikeys.get_apikey` | API key + scope | `admin` | - | `ApiKeyRead` | 200/404【F:app/routers/apikeys.py†L116-L128】 |
| DELETE | /apikeys/{api_key_id} | `apikeys.revoke_apikey` | API key + scope | `admin` | - | - | 204/404【F:app/routers/apikeys.py†L131-L173】 |

## D. Data model & states
| Entity | Key fields & contraintes | Notes |
| --- | --- | --- |
| User | `username`, `email` uniques, `is_active` | Relations transactions envoyées/reçues (cascade).【F:app/models/user.py†L11-L22】 |
| ApiKey | `prefix`, `key_hash` uniques, `scope`, dates | Enum `ApiScope`, audit à chaque usage via `require_api_key`.【F:app/models/api_key.py†L12-L31】【F:app/security.py†L113-L127】 |
| AuditLog | `actor`, `action`, `entity_id`, `data_json`, `at` | Stocke toutes les mutations critiques.【F:app/models/audit.py†L10-L20】 |
| AllowedRecipient | `owner_id`/`recipient_id` unique | Base allowlist pour transferts restreints.【F:app/models/allowlist.py†L8-L15】 |
| CertifiedAccount | `user_id` unique, `level`, `certified_at` | Supporte montée de niveau avec audit.【F:app/models/certified.py†L18-L25】【F:app/services/transactions.py†L79-L107】 |
| Transaction | `sender_id`, `receiver_id`, `amount`, `status`, `idempotency_key` | `Numeric(18,2)` + audit création & alertes.【F:app/models/transaction.py†L20-L37】【F:app/services/transactions.py†L110-L182】 |
| EscrowAgreement | `client_id`, `provider_id`, `amount_total`, `status`, `deadline_at` | Événements JSON + audits transitions.【F:app/models/escrow.py†L23-L69】【F:app/services/escrow.py†L168-L213】 |
| EscrowDeposit | `escrow_id`, `amount`, `idempotency_key` unique | Idempotence + audit `ESCROW_DEPOSITED`.【F:app/models/escrow.py†L45-L55】【F:app/services/escrow.py†L101-L150】 |
| EscrowEvent | `escrow_id`, `kind`, `data_json`, `at` | Timeline complète des actions escrow.【F:app/models/escrow.py†L58-L69】 |
| Milestone | `escrow_id`, `idx` unique, `amount`, `status`, geofence | Montants en `Numeric`, statut aligné sur proofs/paiements.【F:app/models/milestone.py†L22-L47】 |
| Proof | `escrow_id`, `milestone_id`, `sha256` unique | Métadonnées JSON, suivi statut preuve.【F:app/models/proof.py†L10-L23】 |
| Payment | `escrow_id`, `amount`, `status`, `psp_ref`, `idempotency_key` | Numeric + audits `EXECUTE_PAYOUT` et clôture escrow.【F:app/models/payment.py†L21-L38】【F:app/services/payments.py†L206-L333】 |
| PSPWebhookEvent | `event_id` unique, `kind`, `payload` | Garantit idempotence webhook.【F:app/models/psp_webhook.py†L10-L25】【F:app/services/psp_webhooks.py†L54-L87】 |
| UsageMandate | `sender_id`, `beneficiary_id`, `total_amount`, `status`, `total_spent` | Numeric + audit création/consommation/expiration.【F:app/models/usage_mandate.py†L30-L65】【F:app/services/mandates.py†L91-L175】 |
| AllowedPayee | `escrow_id`, `payee_ref` unique, limites `daily/total`, compteurs | Numeric, audit `ADD_ALLOWED_PAYEE`, resets journaliers.【F:app/models/allowed_payee.py†L11-L32】【F:app/services/usage.py†L23-L77】 |
| SpendCategory & Merchant | `code`/`name` uniques, `category_id`, `is_certified` | Audits `SPEND_*` + validations de cohérence.【F:app/models/spend.py†L13-L160】【F:app/services/spend.py†L98-L166】 |

State machines :
- Escrow : `DRAFT` → `FUNDED` → `RELEASABLE` → `RELEASED/REFUNDED/CANCELLED`, déclenché par dépôts, preuves, paiements audités.【F:app/models/escrow.py†L12-L38】【F:app/services/escrow.py†L168-L213】
- Milestone : `WAITING` → `PENDING_REVIEW` → `PAID` / `REJECTED`, orchestré par proofs et paiements.【F:app/models/milestone.py†L11-L45】【F:app/services/proofs.py†L139-L214】【F:app/services/payments.py†L206-L333】
- Payment : `PENDING` → `SENT` → `SETTLED/ERROR`, via `execute_payout` et webhooks PSP.【F:app/models/payment.py†L11-L38】【F:app/services/payments.py†L84-L283】【F:app/services/psp_webhooks.py†L38-L87】
- UsageMandate : `ACTIVE` → `CONSUMED/EXPIRED`, consommation atomique + cron d’expiration audité.【F:app/models/usage_mandate.py†L22-L65】【F:app/services/spend.py†L229-L413】【F:app/services/mandates.py†L150-L175】

## E. Stability results
- `alembic upgrade head` exécuté sans erreur (chaîne linéaire jusqu’à `8b7e_add_api_keys`).【bd9fa7†L1-L12】
- `alembic current` & `alembic heads` confirment l’absence de drift (head unique).【7f15c0†L1-L4】【68200f†L1-L2】
- `pytest -q` : 49 tests verts, un avertissement Pydantic V2 (config class-based).【7afb09†L1-L10】
- Revue statique manuelle : pas de `@app.on_event`, dépendances async évitent le blocage, mais voir risques sur autorisations spend et identités d’audit.

## F. Security & integrity
- AuthN/Z : `require_api_key` journalise chaque appel, interdit la clé legacy hors ENV `dev/local` et autorise explicitement `admin`/`support`/`sender` via `require_scope` (sets).【F:app/config.py†L11-L17】【F:app/security.py†L31-L149】
- Validation input : schémas Pydantic imposent montants positifs, devise, limites d’usage et formats proofs, réduisant l’injection de données incohérentes.【F:app/schemas/spend.py†L12-L140】【F:app/schemas/mandates.py†L12-L88】【F:app/schemas/proof.py†L7-L40】
- Idempotence & transactions : dépôts, paiements, usage spend, transactions et webhooks réutilisent `get_existing_by_key` et contraintes uniques pour éviter les doublons.【F:app/services/idempotency.py†L12-L47】【F:app/services/escrow.py†L101-L165】【F:app/services/payments.py†L84-L283】【F:app/services/usage.py†L97-L210】
- PSP & secrets : secret obligatoire au démarrage, HMAC SHA-256 + dérive temporelle ±5 min, logs d’échec détaillés et stockage structuré des événements.【F:app/main.py†L23-L64】【F:app/services/psp_webhooks.py†L14-L87】
- Audit : toutes les mutations critiques (users, spend, allowlist, transactions, mandats, paiements, usage spend, proofs) écrivent dans `AuditLog`; lacunes : identification acteur générique pour le back-office et absence d’audit lors des doublons `spend/allow` (voir risques).【F:app/utils/audit.py†L10-L30】【F:app/services/spend.py†L112-L226】【F:app/services/transactions.py†L46-L182】【F:app/services/usage.py†L23-L245】

## G. Observability & ops
- Logging structuré (`setup_logging`), CORS centralisé, métriques Prometheus (`/metrics`) et intégration Sentry activables via configuration.【F:app/main.py†L52-L78】【F:app/core/logging.py†L10-L31】【F:app/config.py†L32-L71】
- Lifespan unique (aucun `@app.on_event`), base SQLAlchemy initialisée au démarrage et fermée proprement.【F:app/main.py†L23-L56】
- Scheduler optionnel (`SCHEDULER_ENABLED`) avec avertissement « un seul runner » mais sans verrou distribué natif.【F:app/main.py†L33-L45】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Spend allowed payees | `/spend/allowed` n’effectue aucun contrôle d’appartenance sur l’escrow ciblé ; un scope `sender` malveillant peut greffer un bénéficiaire sur un autre contrat et déclencher des sorties de fonds non désirées. | Critique | Moyenne | P0 | Vérifier que l’API key possède bien l’escrow (jointure sur propriétaire) ou réserver l’endpoint aux scopes back-office avec délégation explicite.【F:app/routers/spend.py†L84-L105】【F:app/services/usage.py†L23-L77】 |
| R2 | Audit back-office | Les audits `CREATE_USER`, `SPEND_*` et `ALLOWLIST_ADD` enregistrent `actor="admin"` ou `"system"`, sans rattacher la clé API ou l’utilisateur réel, rendant la traçabilité RGPD/AML discutable. | Élevé | Élevée | P1 | Inclure l’identifiant/prefix de la clé API ou l’utilisateur support dans `actor`/`data_json` (ex : `actor=f"apikey:{key.id}"`).【F:app/routers/users.py†L37-L44】【F:app/services/spend.py†L112-L224】【F:app/services/transactions.py†L59-L107】 |
| R3 | Spend allow duplicates | Lorsque `AllowedUsage` existe déjà, l’endpoint retourne `status=exists` sans audit ni métrique, masquant les tentatives répétées (fraude ou erreur). | Moyen | Moyenne | P1 | Journaliser un audit `SPEND_ALLOW_EXISTS` et exposer un compteur Prometheus afin de surveiller les collisions. 【F:app/services/spend.py†L198-L226】 |
| R4 | Scheduler | APScheduler en mémoire peut tourner sur plusieurs pods si `SCHEDULER_ENABLED` activé partout (pas de lock distribué). | Moyen | Faible | P2 | Activer le flag sur un seul runner et documenter un job store partagé (Redis/SQL) avant mise à l’échelle. 【F:app/main.py†L33-L45】 |
| R5 | Transactions idempotency | `POST /transactions` accepte l’absence d’`Idempotency-Key`; deux retries réseau peuvent créer des virements dupliqués avant détection manuelle. | Élevé | Moyenne | P1 | Rendre le header obligatoire (400 sinon) ou dériver une clé déterministe signée côté serveur. 【F:app/routers/transactions.py†L45-L59】【F:app/services/transactions.py†L110-L182】 |

## I. Roadmap to MVP-ready
- P0 :
  - Restreindre `/spend/allowed` aux propriétaires légitimes (vérification DB) ou aux scopes back-office, avec tests négatifs pour un escrow tiers.【F:app/services/usage.py†L23-L90】
- P1 :
  - Enrichir `log_audit` avec l’identifiant de clé API/acteur réel et ajouter un audit pour les collisions `spend/allow`.【F:app/utils/audit.py†L10-L30】【F:app/services/spend.py†L198-L226】
  - Imposer `Idempotency-Key` sur `POST /transactions` et couvrir les retries dans les tests AnyIO.【F:app/routers/transactions.py†L45-L59】
- P2 :
  - Prévoir un verrou distribué ou un job store partagé pour APScheduler, avec alerte si plusieurs instances actives.【F:app/main.py†L33-L45】
  - Documenter la rotation du `PSP_WEBHOOK_SECRET` et fournir un endpoint de test signé pour monitoring.【F:app/routers/psp.py†L20-L61】

**Verdict : GO conditionnel** — corriger R1 (contrôle d’appartenance sur `/spend/allowed`) avant exposition à des utilisateurs externes.

## Evidence
- `alembic upgrade head`【bd9fa7†L1-L12】
- `alembic current`【7f15c0†L1-L4】
- `alembic heads`【68200f†L1-L2】
- `pytest -q`【7afb09†L1-L10】
