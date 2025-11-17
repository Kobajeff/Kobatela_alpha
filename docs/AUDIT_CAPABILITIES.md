# Kobatela_alpha — Capability & Stability Audit (2025-11-13)

## A. Executive summary
- Forces :
  - RBAC granulaire : les routes antifraude et catalogue (`/transactions`, `/spend/categories|merchants|allow|allowed`) sont limitées aux scopes `admin` ou `support`, tandis que les dépenses exigent un en-tête `Idempotency-Key` explicite.【F:app/routers/transactions.py†L20-L58】【F:app/routers/spend.py†L33-L140】
  - Usage conditionnel robuste : les dépenses vérifient l’existence d’un payee, verrouillent pessimiste `AllowedPayee` et auditent chaque rejet ou succès.【F:app/services/usage.py†L40-L246】
  - Cycle paiement homogène : `execute_payment`, la dépense usage et le webhook PSP convergent vers `finalize_payment_settlement`, qui règle le paiement, crée les événements et ferme l’escrow lorsque tous les jalons sont payés.【F:app/services/payments.py†L205-L392】【F:app/services/psp_webhooks.py†L70-L138】
  - Audit centralisé : `log_audit` est appelé par la création d’utilisateurs, le catalogue spend et les services transactions afin de tracer chaque mutation sensible.【F:app/utils/audit.py†L10-L30】【F:app/services/spend.py†L112-L225】【F:app/services/transactions.py†L20-L118】【F:app/routers/users.py†L17-L47】
  - Clé legacy maîtrisée : `DEV_API_KEY` n’est acceptée que lorsque `ENV=dev`, sinon l’API renvoie `LEGACY_KEY_FORBIDDEN` et journalise l’usage en mode local.【F:app/security.py†L31-L131】【F:app/utils/apikey.py†L31-L48】
- Risques :
  - Attribution incomplète : plusieurs audits back-office (`CREATE_USER`, `SPEND_*`, `ALLOWLIST_ADD`) fixent `actor="admin"/"system"`, ce qui empêche de rattacher l’action à une clé API précise (P1 conformité).【F:app/routers/users.py†L37-L44】【F:app/services/spend.py†L112-L225】【F:app/services/transactions.py†L44-L96】
  - Collisions `spend/allow` silencieuses : en cas de doublon, l’endpoint retourne `status="exists"` sans audit ni métrique, masquant des tentatives répétées (P1).【F:app/services/spend.py†L184-L225】
  - Idempotence optionnelle sur `/spend/purchases` : l’en-tête reste facultatif, et un retry réseau peut créer un achat dupliqué avant intervention humaine (P1).【F:app/routers/spend.py†L62-L74】【F:app/services/spend.py†L229-L413】
  - Scheduler en mémoire : APScheduler démarre en mode local sans verrou distribué ; hors dev un simple oubli de configuration peut lancer plusieurs instances (P2).【F:app/main.py†L33-L74】
  - Ajout de payee impersonnel : `add_allowed_payee` enregistre `actor="system"` sans contextualiser la clé API support à l’origine de l’ajout (P2 traçabilité).【F:app/services/usage.py†L40-L110】

Readiness score : **85 / 100** — GO conditionnel (prioriser les correctifs P1 avant onboarding multi-comptes).

## B. Capability map (current, concrete)
### B.1 Feature coverage
| Feature | Implemented endpoints/modules | Status | Notes |
| --- | --- | --- | --- |
| Santé & métadonnées | `GET /health` → `health.healthcheck` | Implémenté | Ping JSON sans auth pour monitoring.【F:app/routers/health.py†L4-L11】 |
| Gestion clés API | `POST/GET/DELETE /apikeys` | Implémenté | Admin-only, génération hashée + audit création/révocation.【F:app/routers/apikeys.py†L62-L173】 |
| Gestion utilisateurs | `POST/GET /users` | Implémenté | Clés `admin/support`, audit `CREATE_USER` via `log_audit`.【F:app/routers/users.py†L17-L47】 |
| Allowlist & certification | `POST /allowlist`, `POST /certified` | Implémenté | Scopes `admin`, déduplication et audit détaillé.【F:app/routers/transactions.py†L20-L42】【F:app/services/transactions.py†L44-L118】 |
| Transactions restreintes | `POST/GET /transactions` | Implémenté | Admin-only + `Idempotency-Key` obligatoire et alertes antifraude.【F:app/routers/transactions.py†L20-L76】【F:app/services/transactions.py†L110-L182】 |
| Escrow lifecycle | `/escrows/*` | Implémenté | Création, dépôts idempotents, transitions client/provider auditées.【F:app/routers/escrow.py†L13-L68】【F:app/services/escrow.py†L168-L213】 |
| Mandats d’usage | `/mandates`, `/mandates/cleanup` | Implémenté | Validation bénéficiaires/merchants, audit création/expiration.【F:app/routers/mandates.py†L13-L32】【F:app/services/mandates.py†L91-L175】 |
| Catalogue spend | `/spend/categories`, `/spend/merchants` | Implémenté | Restreint `admin/support`, audits `SPEND_*_CREATED`, contrôle de cohérence.【F:app/routers/spend.py†L33-L50】【F:app/services/spend.py†L98-L166】 |
| Allow usage | `POST /spend/allow` | Implémenté | Règles admin/support, vérifie merchant/category, retourne `added`/`exists`.【F:app/routers/spend.py†L53-L59】【F:app/services/spend.py†L184-L225】 |
| Purchases conditionnels | `POST /spend/purchases` | Implémenté | Consommation mandat atomique, audits mandat & achat (idempotence facultative).【F:app/routers/spend.py†L62-L74】【F:app/services/spend.py†L229-L413】 |
| Allowed payees & usage spend | `POST /spend/allowed`, `POST /spend` | Implémenté | Admin/support pour l’ajout, dépense verrouillée `FOR UPDATE` + audit des rejets.【F:app/routers/spend.py†L84-L140】【F:app/services/usage.py†L40-L246】 |
| Proof pipeline | `POST /proofs`, `POST /proofs/{id}/decision` | Implémenté | Validation, audit & transitions milestone/proof.【F:app/routers/proofs.py†L12-L37】【F:app/services/proofs.py†L139-L214】 |
| Paiements & PSP | `POST /payments/execute/{id}`, `POST /psp/webhook` | Implémenté | Paiements idempotents, audit `EXECUTE_PAYOUT`, HMAC PSP obligatoire.【F:app/routers/payments.py†L11-L22】【F:app/services/payments.py†L205-L392】【F:app/services/psp_webhooks.py†L70-L138】 |
| Back-office alerting | `GET /alerts` | Implémenté | Lecture filtrable réservée à `admin/support`.【F:app/routers/alerts.py†L12-L25】 |

### B.2 Supported end-to-end flows (today)
- Mandat diaspora → achat conditionnel : `/users` (création) → `/mandates` (activation + audit) → `/spend/purchases` (consommation mandat, réutilisation idempotente).【F:app/routers/users.py†L17-L47】【F:app/services/mandates.py†L91-L175】【F:app/services/spend.py†L229-L413】
- Escrow avec preuves et paiements : `/escrows` → `/escrows/{id}/deposit` (idempotent) → `/proofs` → `/payments/execute/{id}` puis `_finalize_escrow_if_paid` via `finalize_payment_settlement` clôture l’escrow et journalise.【F:app/routers/escrow.py†L13-L63】【F:app/services/proofs.py†L139-L214】【F:app/services/payments.py†L205-L392】
- Flux PSP : `/psp/webhook` vérifie HMAC + timestamp, persiste l’événement et appelle `finalize_payment_settlement` pour harmoniser les états paiements/escrows.【F:app/services/psp_webhooks.py†L21-L109】【F:app/services/payments.py†L288-L392】

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request | Response | Codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | /health | `health.healthcheck` | Aucune | - | - | `{status}` | 200【F:app/routers/health.py†L4-L11】 |
| POST | /users | `users.create_user` | API key + scope | `admin`, `support` | `UserCreate` | `UserRead` | 201/400【F:app/routers/users.py†L17-L47】 |
| POST | /allowlist | `transactions.add_to_allowlist` | API key + scope | `admin` | `AllowlistCreate` | `{status}` | 201/200【F:app/routers/transactions.py†L20-L34】 |
| POST | /certified | `transactions.add_certification` | API key + scope | `admin` | `CertificationCreate` | `{status}` | 201【F:app/routers/transactions.py†L34-L42】 |
| POST | /transactions | `transactions.post_transaction` | API key + scope | `admin` | `TransactionCreate` + `Idempotency-Key` requis | `TransactionRead` | 201/400【F:app/routers/transactions.py†L45-L59】 |
| GET | /transactions/{id} | `transactions.get_transaction` | API key + scope | `admin` | - | `TransactionRead` | 200/404【F:app/routers/transactions.py†L62-L76】 |
| POST | /escrows | `escrow.create_escrow` | API key + scope | `sender`, `admin` | `EscrowCreate` | `EscrowRead` | 201【F:app/routers/escrow.py†L13-L22】 |
| POST | /escrows/{id}/deposit | `escrow.deposit` | API key + scope | `sender`, `admin` | `EscrowDepositCreate` + `Idempotency-Key?` | `EscrowRead` | 200【F:app/routers/escrow.py†L25-L32】 |
| POST | /escrows/{id}/client-approve | `escrow.client_approve` | API key + scope | `sender`, `admin` | `EscrowActionPayload?` | `EscrowRead` | 200【F:app/routers/escrow.py†L40-L46】 |
| POST | /alerts | `alerts.list_alerts` | API key + scope | `admin`, `support` | Query `type?` | `list[AlertRead]` | 200【F:app/routers/alerts.py†L12-L25】 |
| POST | /mandates | `mandates.create_mandate` | API key + scope | `sender`, `admin` | `UsageMandateCreate` | `UsageMandateRead` | 201【F:app/routers/mandates.py†L13-L24】 |
| POST | /spend/categories | `spend.create_category` | API key + scope | `admin`, `support` | `SpendCategoryCreate` | `SpendCategoryRead` | 201【F:app/routers/spend.py†L33-L40】 |
| POST | /spend/merchants | `spend.create_merchant` | API key + scope | `admin`, `support` | `MerchantCreate` | `MerchantRead` | 201【F:app/routers/spend.py†L43-L50】 |
| POST | /spend/allow | `spend.allow_usage` | API key + scope | `admin`, `support` | `AllowedUsageCreate` | `{status}` | 201/200【F:app/routers/spend.py†L53-L59】 |
| POST | /spend/allowed | `spend.add_allowed_payee` | API key + scope | `admin`, `support` | `AddPayeeIn` | Payee dict | 201/409【F:app/routers/spend.py†L84-L140】【F:app/services/usage.py†L40-L110】 |
| POST | /spend | `spend.spend` | API key + scope | `sender`, `admin` | `SpendIn` + `Idempotency-Key` requis | Paiement dict | 200/400/409【F:app/routers/spend.py†L115-L140】【F:app/services/usage.py†L115-L246】 |
| POST | /payments/execute/{id} | `payments.execute_payment` | API key + scope | `sender`, `admin` | - | `PaymentRead` | 200/404/409【F:app/routers/payments.py†L11-L22】【F:app/services/payments.py†L205-L287】 |
| POST | /psp/webhook | `psp.webhook` | Secret PSP + optional API key | - | Raw JSON + headers | `{ok, event_id}` | 200/401/503【F:app/routers/psp.py†L20-L61】 |

## D. Data model & states
| Entity | Key fields & contraintes | Notes |
| --- | --- | --- |
| User | `username`, `email` uniques, `is_active` | Audit `CREATE_USER` mais acteur générique.【F:app/models/user.py†L11-L22】【F:app/routers/users.py†L37-L47】 |
| ApiKey | `prefix`, `key_hash` uniques, `scope`, dates | Audit usage avec `actor=f"apikey:{id}"` et rejet clé legacy hors dev.【F:app/models/api_key.py†L12-L31】【F:app/security.py†L31-L131】 |
| AllowedRecipient | `(owner_id, recipient_id)` unique | Retourne `exists` sans audit en doublon.【F:app/models/allowlist.py†L8-L15】【F:app/services/transactions.py†L44-L96】 |
| CertifiedAccount | `user_id` unique, `level`, `certified_at` | Audit `CERTIFICATION_UPDATE` sur création/mise à jour.【F:app/models/certified.py†L18-L25】【F:app/services/transactions.py†L79-L107】 |
| Transaction | `sender_id`, `receiver_id`, `amount`, `status`, `idempotency_key` | Enum `COMPLETED`, idempotence obligatoire côté API.【F:app/models/transaction.py†L20-L37】【F:app/routers/transactions.py†L45-L59】 |
| EscrowAgreement | `client_id`, `provider_id`, `amount_total`, `status`, `deadline_at` | Événements JSON + audits transitions.【F:app/models/escrow.py†L23-L69】【F:app/services/escrow.py†L168-L213】 |
| Milestone | `escrow_id`, `idx` unique, `amount`, `status` | Convergence proofs/paiements via `finalize_payment_settlement`.【F:app/models/milestone.py†L22-L47】【F:app/services/payments.py†L288-L392】 |
| Payment | `escrow_id`, `amount`, `status`, `psp_ref`, `idempotency_key` | Numeric + audits `EXECUTE_PAYOUT` et `PAYMENT_SETTLED`.【F:app/models/payment.py†L21-L38】【F:app/services/payments.py†L205-L392】 |
| AllowedPayee | `escrow_id`, `payee_ref` unique, limites `daily/total`, compteurs | Ajout audité (actor "system"), consommation verrouillée FOR UPDATE.【F:app/models/allowed_payee.py†L11-L32】【F:app/services/usage.py†L40-L210】 |
| SpendCategory & Merchant | Codes/refs uniques | Audits `SPEND_CATEGORY_CREATED` & `SPEND_MERCHANT_CREATED`.【F:app/models/spend.py†L13-L160】【F:app/services/spend.py†L98-L166】 |

State machines :
- Escrow : `DRAFT` → `FUNDED` → `RELEASABLE` → `RELEASED/REFUNDED/CANCELLED`, finalisé automatiquement quand tous les jalons sont payés.【F:app/models/escrow.py†L12-L69】【F:app/services/payments.py†L353-L390】
- Milestone : `WAITING` → `PENDING_REVIEW` → `PAID`/`REJECTED`, orchestré par proofs et paiements.【F:app/models/milestone.py†L22-L47】【F:app/services/proofs.py†L139-L214】
- Payment : `PENDING` → `SENT` → `SETTLED/ERROR`, harmonisé par `finalize_payment_settlement` ou le webhook PSP.【F:app/models/payment.py†L11-L38】【F:app/services/payments.py†L205-L392】【F:app/services/psp_webhooks.py†L70-L138】
- UsageMandate : `ACTIVE` → `CONSUMED/EXPIRED`, consommation atomique via `create_purchase` et cron d’expiration.【F:app/models/usage_mandate.py†L30-L65】【F:app/services/spend.py†L229-L413】【F:app/services/mandates.py†L150-L175】

## E. Stability results
- `alembic current --verbose` (SQLite dev) : aucun drift signalé, base fraîche sans révision appliquée.【823cf6†L1-L4】
- `alembic heads` → `8b7e_add_api_keys` (head unique).【dae9a3†L1-L2】
- `pytest -q` : 51 tests verts, 1 avertissement Pydantic V2 (config class-based).【d1eb61†L1-L10】
- Revue statique : aucun `@app.on_event`, vérifications d’attente `Idempotency-Key` sur `/spend` et `/transactions`, mais idempotence facultative sur `/spend/purchases` (voir risques).

## F. Security & integrity
- AuthN/Z : `require_api_key` journalise chaque appel avec l’identifiant de la clé, et `require_scope` accepte des ensembles d’`ApiScope` pour restreindre chaque route critique.【F:app/security.py†L31-L154】
- Validation input : schémas Pydantic imposent montants positifs, devise ISO et formats proofs/mandats, limitant les injections incohérentes.【F:app/schemas/spend.py†L12-L140】【F:app/schemas/mandates.py†L12-L88】【F:app/schemas/proof.py†L7-L40】
- Idempotence & transactions : dépôts, paiements, usage spend et transactions réutilisent `get_existing_by_key` et contraintes uniques pour éviter les doublons, avec verrou `FOR UPDATE` sur les payees.【F:app/services/escrow.py†L101-L165】【F:app/services/payments.py†L205-L392】【F:app/services/usage.py†L97-L246】
- PSP & secrets : démarrage bloquant sans `PSP_WEBHOOK_SECRET`, HMAC SHA-256 + timestamp ±5 min et persistance idempotente des événements.【F:app/main.py†L23-L64】【F:app/services/psp_webhooks.py†L21-L109】
- Audit : toutes les mutations critiques écrivent dans `AuditLog`, mais les actions back-office utilisent encore des acteurs génériques (cf. risques).【F:app/utils/audit.py†L10-L30】【F:app/services/spend.py†L112-L225】【F:app/services/transactions.py†L44-L118】

### Encadré DEV_API_KEY
- La clé legacy n’est acceptée que lorsque `ENV` vaut `dev` et que `DEV_API_KEY_ALLOWED` est à `True`; dans ce cas `require_api_key` l’enregistre comme acteur `legacy-apikey` puis journalise `LEGACY_API_KEY_USED`.【F:app/security.py†L42-L83】
- Dans tout autre environnement (staging/prod), FastAPI renvoie immédiatement `LEGACY_KEY_FORBIDDEN` (HTTP 401) sans requêter la base et force l’équipe à utiliser des clés nominatives sécurisées. Chaque rejet reste traçable puisque l’exception encode le code d’erreur dédié dans `error_response`.【F:app/security.py†L60-L71】【F:app/utils/errors.py†L5-L22】

## G. Observability & ops
- Logging structuré et Sentry optionnel via `app/config.py`; CORS et métriques exposées par la configuration centrale.【F:app/main.py†L52-L78】【F:app/config.py†L32-L71】
- Lifespan unique (`lifespan` context manager) : initialisation DB et scheduler encapsulés sans `@app.on_event` legacy.【F:app/main.py†L23-L74】
- Scheduler optionnel (`SCHEDULER_ENABLED`) avec avertissement clair lorsqu’il est activé hors dev, rappelant la contrainte “un seul runner”.【F:app/main.py†L33-L74】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Audit back-office | Acteurs `admin/system` dans `CREATE_USER`, `SPEND_*`, `ALLOWLIST_ADD` empêchent de rattacher l’action à une clé API réelle (traçabilité/AML).【F:app/routers/users.py†L37-L44】【F:app/services/spend.py†L112-L225】【F:app/services/transactions.py†L44-L96】 | Élevé | Élevée | P1 | Propager l’identifiant/prefix de la clé API via `log_audit` (ex : `actor=f"apikey:{key.id}"`). |
| R2 | Allow usage | Les doublons `AllowedUsage` renvoient `status="exists"` sans audit, masquant des tentatives répétées (fraude ou erreur).【F:app/services/spend.py†L184-L225】 | Moyen | Moyenne | P1 | Émettre un audit `SPEND_ALLOW_EXISTS` et, idéalement, exposer un compteur Prometheus. |
| R3 | Purchases | `/spend/purchases` n’impose pas `Idempotency-Key`; un retry réseau peut créer un achat double avant réconciliation.【F:app/routers/spend.py†L62-L74】【F:app/services/spend.py†L229-L413】 | Critique | Moyenne | P1 | Rendre l’en-tête obligatoire (alignement sur `/spend`) ou dériver une clé déterministe signée. |
| R4 | Scheduler | APScheduler en mémoire risque d’être lancé sur plusieurs pods si le flag est activé partout (pas de lock distribué).【F:app/main.py†L33-L74】 | Moyen | Faible | P2 | Activer `SCHEDULER_ENABLED` sur un seul runner et prévoir un job store partagé (Redis/SQL) avant montée en charge. |
| R5 | Allowed payees | `add_allowed_payee` trace `actor="system"` sans référence à la clé support à l’origine de la modification, compliquant les enquêtes.【F:app/services/usage.py†L40-L110】 | Moyen | Faible | P2 | Passer l’identifiant API à `log_audit` depuis le router (ou enrichir `actor`). |

## I. Roadmap to MVP-ready
- P0 :
  - Aucun P0 ouvert après verrouillage RBAC, mais surveiller toute régression sur `/spend/allowed` lors des évolutions futures.【F:app/routers/spend.py†L84-L105】
- P1 :
  - Enrichir `log_audit` avec l’identifiant de la clé API pour les actions back-office (R1, R5).【F:app/utils/audit.py†L10-L30】
  - Ajouter un audit et des métriques sur les collisions `spend/allow`; rendre `Idempotency-Key` obligatoire pour `/spend/purchases` (R2, R3).【F:app/services/spend.py†L184-L225】【F:app/routers/spend.py†L62-L74】
- P2 :
  - Préparer un job store partagé ou un verrou distribué pour APScheduler avant déploiement multi-pods (R4).【F:app/main.py†L33-L74】
  - Étendre l’audit payee pour inclure la clé support ayant initié l’opération (R5).【F:app/services/usage.py†L40-L110】

**Verdict : GO conditionnel** — viser l’enrichissement des audits et l’idempotence achats avant ouverture à de nouveaux partenaires.

## Evidence
- `alembic current --verbose`【823cf6†L1-L4】
- `alembic heads`【dae9a3†L1-L2】
- `pytest -q`【d1eb61†L1-L10】
