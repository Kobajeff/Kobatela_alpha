# Kobatela_alpha — Capability & Stability Audit (2025-11-13)

## A. Executive summary
- Forces :
  - Modélisation monétaire homogène en `Numeric(18,2)` avec contraintes de positivité sur transactions, paiements, séquestres, achats et mandats, supprimant tout recours aux floats pour l’argent.【F:app/models/transaction.py†L5-L37】【F:app/models/payment.py†L5-L38】【F:app/models/escrow.py†L33-L68】【F:app/models/spend.py†L37-L83】【F:app/models/usage_mandate.py†L33-L66】
  - Parcours idempotents de bout en bout (dépôts, achats, paiements, webhooks) grâce aux helpers partagés et aux verrous applicatifs sur les clés uniques.【F:app/services/idempotency.py†L12-L50】【F:app/services/escrow.py†L101-L165】【F:app/services/spend.py†L187-L341】【F:app/services/usage.py†L80-L236】【F:app/services/payments.py†L84-L203】【F:app/services/psp_webhooks.py†L20-L83】
  - Journalisation métier détaillée : chaque transition critique (escrow, mandat, achat, dépense usage, paiement) émet un `AuditLog` structuré.【F:app/services/escrow.py†L74-L248】【F:app/services/mandates.py†L23-L176】【F:app/services/spend.py†L342-L369】【F:app/services/usage.py†L205-L230】【F:app/services/payments.py†L229-L259】
  - Pipeline preuves riche : validation EXIF/GPS, tolérances temporelles, geofence haversine et auto-approbation contrôlée déclenchant les paiements.【F:app/services/proofs.py†L63-L246】【F:app/services/rules.py†L15-L107】
  - Démarrage maîtrisé par lifespan : logging JSON unifié, secret PSP obligatoire, moteur SQL initialisé et job d’expiration planifié avant d’ouvrir les routes.【F:app/main.py†L23-L71】【F:app/core/logging.py†L10-L31】【F:app/services/cron.py†L12-L33】
- Risques :
  - Les routes dépendant de `require_scope("sender")` n’acceptent aucune clé non admin : la dépendance attend un `set[ApiScope]`, donc tous les appels métier renverront 403 une fois les clés legacy désactivées (P0).【F:app/security.py†L83-L100】【F:app/routers/escrow.py†L12-L63】【F:app/routers/spend.py†L22-L105】【F:app/routers/mandates.py†L12-L31】
  - La clé `DEV_API_KEY` reste acceptée comme passe-partout dès que `KOB_ENV=dev`, sans garde complémentaire : fuite ou mauvais paramétrage = compromission totale (P0).【F:app/config.py†L11-L63】【F:app/security.py†L35-L57】
  - Les endpoints d’allowlist et de certification modifient la sécurité sans aucune trace dans `AuditLog`, contraire aux exigences de traçabilité (P0).【F:app/routers/transactions.py†L27-L64】【F:app/services/transactions.py†L34-L86】
  - La clôture automatique d’un escrow payé met à jour le statut sans `commit`, laissant l’événement « CLOSED » volatil (P1).【F:app/services/payments.py†L280-L303】
  - L’APScheduler tourne dans chaque worker FastAPI, sans verrou de distribution ni option de désactivation, risquant des expirations doublées (P2).【F:app/main.py†L31-L45】【F:app/services/cron.py†L12-L33】

Readiness score: **55 / 100** — NO-GO tant que les P0 (scope cassé, clé dev universelle, absence d’audit sur allowlist/certif) ne sont pas corrigés.

## B. Capability map (current, concrete)
### B.1 Feature coverage
| Feature | Implemented endpoints/modules | Status | Notes |
| --- | --- | --- | --- |
| Santé & métadonnées | `GET /health` → `health.healthcheck` | Implémenté | Ping JSON sans authentification pour monitoring basique.【F:app/routers/health.py†L4-L11】 |
| Gestion clés API | `POST/GET/DELETE /apikeys` | Implémenté | Création, lecture et révocation (204) réservées au scope admin avec journaux dédiés.【F:app/routers/apikeys.py†L62-L173】 |
| Gestion utilisateurs | `POST /users`, `GET /users/{id}` | Implémenté | CRUD minimal protégé par clé API générique, pas de rôle fin (dépend du scope cassé).【F:app/routers/users.py†L11-L31】 |
| Allowlist & certification | `/allowlist`, `/certified` | Implémenté | Ajout/déduplication et mise à jour du niveau certifié, mais sans audit (voir risques).【F:app/routers/transactions.py†L27-L64】 |
| Transactions restreintes | `POST/GET /transactions` | Implémenté | Idempotency-Key, audit et alertes en cas de destinataire non autorisé.【F:app/routers/transactions.py†L66-L88】【F:app/services/transactions.py†L25-L96】 |
| Escrow lifecycle | `/escrows/*` | Implémenté | Création, dépôt idempotent, transitions client/provider et lecture directe (bloqué par scope bug).【F:app/routers/escrow.py†L12-L63】【F:app/services/escrow.py†L60-L250】 |
| Mandats d’usage | `/mandates`, `/mandates/cleanup` | Implémenté | Création auditée, anti-doublon DB + cron d’expiration périodique.【F:app/routers/mandates.py†L12-L31】【F:app/services/mandates.py†L68-L176】 |
| Spend catalogues | `/spend/categories`, `/spend/merchants`, `/spend/allow` | Implémenté | Vérifications d’unicité et de cohérence avant commit, retour statut clair.【F:app/routers/spend.py†L22-L42】【F:app/services/spend.py†L97-L185】 |
| Purchases conditionnels | `POST /spend/purchases` | Implémenté | Vérifie mandat actif + allowlist/certification et décrémente atomiquement.【F:app/routers/spend.py†L44-L51】【F:app/services/spend.py†L187-L341】 |
| Allowed payees & usage spend | `POST /spend/allowed`, `POST /spend` | Implémenté | Gestion payees + dépenses idempotentes avec limites quotidiennes/totales et audit.【F:app/routers/spend.py†L53-L105】【F:app/services/usage.py†L23-L236】 |
| Preuves & milestones | `/proofs`, `/proofs/{id}/decision` | Implémenté | Validation EXIF/GPS, auto-approbation et déclenchement paiement/fermeture escrow.【F:app/routers/proofs.py†L11-L33】【F:app/services/proofs.py†L45-L320】 |
| Paiements & PSP | `/payments/execute/{id}`, `/psp/webhook` | Implémenté | Exécution idempotente, événements escrow et webhooks HMAC + audit Payment.【F:app/routers/payments.py†L10-L21】【F:app/routers/psp.py†L20-L61】【F:app/services/psp_webhooks.py†L54-L145】 |

### B.2 Supported end-to-end flows (today)
- Mandat diaspora → achat conditionnel : `/users` → `/mandates` (anti-doublon + audit) → `/spend/purchases` (mandate consume + audit).【F:app/routers/users.py†L11-L31】【F:app/services/mandates.py†L91-L176】【F:app/services/spend.py†L257-L371】
- Escrow avec preuves photo : `/escrows` → `/escrows/{id}/deposit` (idempotent) → `/proofs` → paiement automatique et event `CLOSED` quand tous les jalons sont payés.【F:app/routers/escrow.py†L12-L63】【F:app/services/escrow.py†L101-L250】【F:app/services/proofs.py†L139-L412】
- Paiement manuel + webhook PSP : `/payments/execute/{id}` (génère `EXECUTE_PAYOUT`) → `/psp/webhook` (HMAC, settle/erreur, audit).【F:app/services/payments.py†L205-L277】【F:app/routers/psp.py†L20-L61】【F:app/services/psp_webhooks.py†L85-L144】

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request | Response | Codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | /health | `health.healthcheck`【F:app/routers/health.py†L4-L11】 | Aucune | - | - | `dict[str,str]` | 200 |
| POST | /users | `users.create_user`【F:app/routers/users.py†L14-L22】 | Clé API (`require_api_key`)【F:app/routers/users.py†L11-L31】 | n/a | `UserCreate` | `UserRead` | 201 |
| GET | /users/{user_id} | `users.get_user`【F:app/routers/users.py†L25-L31】 | Clé API | n/a | - | `UserRead` | 200/404 |
| POST | /allowlist | `transactions.add_to_allowlist`【F:app/routers/transactions.py†L27-L44】 | Clé API | n/a | `AllowlistCreate` | `{status}` | 201 |
| POST | /certified | `transactions.add_certification`【F:app/routers/transactions.py†L46-L63】 | Clé API | n/a | `CertificationCreate` | `{status}` | 201 |
| POST | /transactions | `transactions.post_transaction`【F:app/routers/transactions.py†L66-L75】 | Clé API | n/a | `TransactionCreate` + `Idempotency-Key` | `TransactionRead` | 201 |
| GET | /transactions/{id} | `transactions.get_transaction`【F:app/routers/transactions.py†L78-L88】 | Clé API | n/a | - | `TransactionRead` | 200/404 |
| POST | /escrows | `escrow.create_escrow`【F:app/routers/escrow.py†L19-L21】 | Clé API + `require_scope("sender")` (cassé)【F:app/routers/escrow.py†L12-L45】【F:app/security.py†L83-L100】 | sender | `EscrowCreate` | `EscrowRead` | 201 |
| POST | /escrows/{id}/deposit | `escrow.deposit`【F:app/routers/escrow.py†L24-L31】 | Clé API + scope sender (cassé) | sender | `EscrowDepositCreate` + `Idempotency-Key` | `EscrowRead` | 200 |
| POST | /escrows/{id}/mark-delivered | `escrow.mark_delivered`【F:app/routers/escrow.py†L34-L36】 | Clé API + scope sender (cassé) | sender | `EscrowActionPayload` | `EscrowRead` | 200 |
| POST | /escrows/{id}/client-approve | `escrow.client_approve`【F:app/routers/escrow.py†L39-L45】 | Clé API + scope sender (cassé) | sender | `EscrowActionPayload?` | `EscrowRead` | 200 |
| POST | /escrows/{id}/client-reject | `escrow.client_reject`【F:app/routers/escrow.py†L48-L54】 | Clé API + scope sender (cassé) | sender | `EscrowActionPayload?` | `EscrowRead` | 200 |
| POST | /escrows/{id}/check-deadline | `escrow.check_deadline`【F:app/routers/escrow.py†L57-L59】 | Clé API + scope sender (cassé) | sender | - | `EscrowRead` | 200 |
| GET | /escrows/{id} | `escrow.read_escrow`【F:app/routers/escrow.py†L62-L67】 | Clé API + scope sender (cassé) | sender | - | `EscrowRead` | 200/404 |
| GET | /alerts | `alerts.list_alerts`【F:app/routers/alerts.py†L11-L19】 | Clé API | n/a | Query `type?` | `list[AlertRead]` | 200 |
| POST | /mandates | `mandates.create_mandate`【F:app/routers/mandates.py†L19-L23】 | Clé API + scope sender (cassé) | sender | `UsageMandateCreate` | `UsageMandateRead` | 201 |
| POST | /mandates/cleanup | `mandates.cleanup_expired_mandates`【F:app/routers/mandates.py†L26-L31】 | Clé API + scope sender (cassé) | sender | - | `{expired:int}` | 202 |
| POST | /spend/categories | `spend.create_category`【F:app/routers/spend.py†L29-L31】 | Clé API + scope sender (cassé) | sender | `SpendCategoryCreate` | `SpendCategoryRead` | 201 |
| POST | /spend/merchants | `spend.create_merchant`【F:app/routers/spend.py†L34-L36】 | Clé API + scope sender (cassé) | sender | `MerchantCreate` | `MerchantRead` | 201 |
| POST | /spend/allow | `spend.allow_usage`【F:app/routers/spend.py†L39-L41】 | Clé API + scope sender (cassé) | sender | `AllowedUsageCreate` | `{status}` | 201 |
| POST | /spend/purchases | `spend.create_purchase`【F:app/routers/spend.py†L44-L50】 | Clé API + scope sender (cassé) | sender | `PurchaseCreate` + `Idempotency-Key?` | `PurchaseRead` | 201 |
| POST | /spend/allowed | `spend.add_allowed_payee`【F:app/routers/spend.py†L53-L78】 | Clé API + scope sender (cassé) | sender | `AddPayeeIn` | dict payee | 201 |
| POST | /spend | `spend.spend`【F:app/routers/spend.py†L81-L103】 | Clé API + scope sender (cassé) | sender | `SpendIn` + `Idempotency-Key?` | dict paiement | 200 |
| POST | /payments/execute/{payment_id} | `payments.execute_payment`【F:app/routers/payments.py†L17-L21】 | Clé API + scope sender (cassé) | sender | - | `PaymentRead` | 200/404 |
| POST | /proofs | `proofs.submit_proof`【F:app/routers/proofs.py†L18-L22】 | Clé API + scope sender (cassé) | sender | `ProofCreate` | `ProofRead` | 201 |
| POST | /proofs/{proof_id}/decision | `proofs.decide_proof`【F:app/routers/proofs.py†L25-L36】 | Clé API + scope sender (cassé) | sender | `ProofDecision` | `ProofRead` | 200/400 |
| POST | /psp/webhook | `psp.psp_webhook`【F:app/routers/psp.py†L20-L61】 | Signature HMAC (secret obligatoire) | PSP | raw JSON | `{ok,event_id,processed_at}` | 200/401/503 |
| POST | /apikeys | `apikeys.create_api_key`【F:app/routers/apikeys.py†L62-L113】 | Clé API + scope admin | admin | `CreateKeyIn` | `ApiKeyCreateOut` | 201 |
| GET | /apikeys/{id} | `apikeys.get_apikey`【F:app/routers/apikeys.py†L116-L128】 | Clé API + scope admin | admin | - | `ApiKeyRead` | 200/404 |
| DELETE | /apikeys/{id} | `apikeys.revoke_apikey`【F:app/routers/apikeys.py†L131-L173】 | Clé API + scope admin | admin | - | `Response 204` | 204/404 |

## D. Data model & states
| Entité | Champs clés | Contraintes / Relations |
| --- | --- | --- |
| User | `username`, `email`, `is_active` | Unicité sur username/email, relations `sent_transactions` & `received_transactions`.【F:app/models/user.py†L8-L21】 |
| ApiKey | `prefix`, `key_hash`, `scope`, `is_active` | Enum `ApiScope`, unique `prefix` et `key_hash`, audit lors de l’usage.【F:app/models/api_key.py†L12-L31】【F:app/security.py†L66-L79】 |
| AuditLog | `actor`, `action`, `entity`, `data_json`, `at` | Trace structurée horodatée, utilisée par services métier.【F:app/models/audit.py†L10-L20】 |
| Alert | `type`, `message`, `payload_json` | Index sur `created_at` et `type`, option `actor_user_id`.【F:app/models/alert.py†L8-L17】 |
| Transaction | `sender_id`, `receiver_id`, `amount`, `status`, `idempotency_key` | `Numeric(18,2)`, contrainte montant>0, index statut, FK utilisateurs.【F:app/models/transaction.py†L20-L37】 |
| AllowedRecipient | `owner_id`, `recipient_id` | Contrainte d’unicité sur la paire owner/recipient.【F:app/models/allowlist.py†L8-L15】 |
| CertifiedAccount | `user_id`, `level`, `certified_at` | Enum `CertificationLevel`, `user_id` unique (1-1).【F:app/models/certified.py†L11-L25】 |
| EscrowAgreement | `client_id`, `provider_id`, `amount_total`, `status` | `Numeric(18,2)`, indices statut/délais, relations `deposits` & `events`.【F:app/models/escrow.py†L23-L68】 |
| EscrowDeposit | `escrow_id`, `amount`, `idempotency_key` | Contrainte montant>0, idempotency unique indexée.【F:app/models/escrow.py†L45-L55】 |
| EscrowEvent | `escrow_id`, `kind`, `idempotency_key`, `data_json` | Chronologie JSON, index sur `kind`.【F:app/models/escrow.py†L58-L69】 |
| Milestone | `escrow_id`, `idx`, `amount`, `status` | `Numeric(18,2)`, contraintes idx/amount>0, geofence optionnelle Float, unique (escrow,idx).【F:app/models/milestone.py†L22-L47】 |
| Proof | `escrow_id`, `milestone_id`, `sha256`, `status` | `sha256` unique, métadonnées JSON, statut par défaut `PENDING`.【F:app/models/proof.py†L10-L24】 |
| Payment | `escrow_id`, `milestone_id`, `amount`, `status`, `idempotency_key` | `Numeric(18,2)`, contraintes >0, indices statut/idempotency, `psp_ref` unique.【F:app/models/payment.py†L21-L39】 |
| PSPWebhookEvent | `event_id`, `psp_ref`, `kind`, `raw_json` | Unique sur `event_id`, timestamps `received_at`/`processed_at`.【F:app/models/psp_webhook.py†L10-L25】 |
| UsageMandate | `sender_id`, `beneficiary_id`, `total_amount`, `status`, `total_spent` | `Numeric(18,2)`, index partiel unique ACTIVE, suivis `total_spent`.【F:app/models/usage_mandate.py†L30-L65】 |
| AllowedPayee | `escrow_id`, `payee_ref`, limites quotidiennes/totales | Unicité `(escrow_id,payee_ref)` + contraintes de positivité.【F:app/models/allowed_payee.py†L11-L32】 |
| AllowedUsage | `owner_id`, `merchant_id/category_id` | Contraintes XOR et unicité par owner+target.【F:app/models/spend.py†L37-L55】 |
| SpendCategory & Merchant | `code`, `name`, `category_id` | Unicité code/nom, relation `merchants` → `spend_categories`.【F:app/models/spend.py†L13-L35】 |
| Purchase | `sender_id`, `merchant_id`, `amount`, `status`, `idempotency_key` | `Numeric(18,2)`, contrainte >0, index statut/idempotency.【F:app/models/spend.py†L64-L83】 |

State machines :
- Escrow : `DRAFT` → `FUNDED` → `RELEASABLE` → `RELEASED`/`REFUNDED`/`CANCELLED` selon livraisons, rejets ou remboursements.【F:app/models/escrow.py†L12-L55】【F:app/services/escrow.py†L168-L251】
- Milestone : `WAITING` → `PENDING_REVIEW`/`APPROVED` → `PAYING` → `PAID`, ou `REJECTED` via décision preuve.【F:app/models/milestone.py†L11-L47】【F:app/services/proofs.py†L172-L361】
- Payment : `PENDING` → `SENT` → `SETTLED` ou `ERROR`, piloté par exécution locale puis webhooks.【F:app/models/payment.py†L11-L38】【F:app/services/psp_webhooks.py†L85-L144】
- Proof : `PENDING` (défaut) → `APPROVED`/`REJECTED` géré par service, auto-approbation possible.【F:app/models/proof.py†L10-L24】【F:app/services/proofs.py†L172-L365】
- UsageMandate : `ACTIVE` → `CONSUMED` ou `EXPIRED`, transitions atomiques via update SQL et cron.【F:app/models/usage_mandate.py†L22-L65】【F:app/services/spend.py†L287-L340】【F:app/services/cron.py†L12-L33】

## E. Stability results
- `alembic upgrade head` appliqué sans erreur sur SQLite, chaîne de migrations linéaire jusqu’à `8b7e_add_api_keys`.【64da94†L1-L13】
- `alembic current` et `alembic heads` confirment l’absence de drift (unique head).【edc437†L1-L4】【679ff4†L1-L3】
- `pytest -q` : 33 tests verts (1 avertissement Pydantic deprecation), couvrant flux escrow/mandat/preuve/paiement.【98d418†L1-L10】
- Revue statique : dépendance `require_scope` invalide (voir risques), absence de commit dans `_finalize_escrow_if_paid`, endpoints allowlist/certif sans audit, sinon respect des `await` (handlers sync) et des conversions `Decimal`.

## F. Security & integrity
- AuthN/Z : `require_api_key` HMAC-signe la clé, mais accepte toujours `DEV_API_KEY` en dev et retourne un sentinelle bypassant les scopes (legacy).【F:app/utils/apikey.py†L31-L45】【F:app/security.py†L35-L57】 L’implémentation de `require_scope` attend un set et échoue pour les appels métiers (P0).【F:app/security.py†L83-L100】
- Entrées validées via Pydantic (montants >0, patterns devise, booléens) pour utilisateurs, transactions, mandats, achats et preuves.【F:app/schemas/user.py†L5-L17】【F:app/schemas/transaction.py†L11-L28】【F:app/schemas/mandates.py†L12-L43】【F:app/schemas/spend.py†L12-L78】【F:app/schemas/proof.py†L7-L33】
- Preuves et fichiers : validations EXIF/GPS, géofence haversine, tolérance temporelle et codes erreur spécifiques avant toute mutation d’état.【F:app/services/proofs.py†L63-L214】【F:app/services/rules.py†L15-L107】
- Paiements PSP : signature HMAC SHA-256 avec protection de dérive temporelle, idempotence par `event_id`, audit sur `PAYMENT_SETTLED/FAILED` et logs de fraude.【F:app/services/psp_webhooks.py†L20-L145】【F:app/routers/psp.py†L29-L60】
- Audit : Escrow, mandats, achats, dépenses usage, paiements et preuves sont logués. Exceptions notables : allowlist/certification sans entrée `AuditLog` (P0).【F:app/services/escrow.py†L74-L248】【F:app/services/mandates.py†L23-L176】【F:app/services/spend.py†L342-L369】【F:app/services/usage.py†L205-L230】【F:app/services/transactions.py†L34-L63】

## G. Observability & ops
- Logging JSON centralisé avec enrichissement `extra`, compatible Prometheus et Sentry conditionnels, CORS configurable via settings.【F:app/main.py†L41-L57】【F:app/core/logging.py†L10-L31】【F:app/config.py†L35-L63】
- Scheduler APScheduler lancé au démarrage (job `expire-mandates` toutes les 60 min) mais sans coordination multi-process (voir risques).【F:app/main.py†L31-L45】【F:app/services/cron.py†L12-L33】
- Config `.env` chargée via `Settings` Pydantic, paramétrage CORS/Sentry/Prometheus/DB/PSP centralisé.【F:app/config.py†L32-L71】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | AuthN/Z | `require_scope("sender")` compare un Enum à une chaîne, rejetant toutes les clés non admin → blocage complet des flux métier après désactivation de la clé legacy. | Élevé (toutes routes métiers 4xx) | Élevée | P0 | Corriger la signature pour accepter `set[ApiScope]`, ajouter tests d’intégration sur clés `sender/support`.【F:app/security.py†L83-L100】【F:app/routers/spend.py†L22-L105】 |
| R2 | AuthN | `DEV_API_KEY` toujours valide et autorisée tant que `KOB_ENV=dev`, ce qui suffit pour exfiltrer toute donnée si le secret fuite. | Critique (compromission API) | Moyenne | P0 | Désactiver par défaut (`DEV_API_KEY_ALLOWED=False` hors dev), journaliser son usage et forcer une clé HMAC dédiée par environnement.【F:app/config.py†L11-L63】【F:app/security.py†L35-L57】 |
| R3 | Transactions | `/allowlist` & `/certified` modifient la politique antifraude sans `AuditLog`, empêchant toute piste d’audit réglementaire. | Élevé (non-conformité, investigations impossibles) | Élevée | P0 | Enregistrer un `AuditLog` (acteur + payload) et envisager une table d’historique pour révocation. Ajouter tests d’audit.【F:app/routers/transactions.py†L27-L63】【F:app/services/transactions.py†L34-L86】 |
| R4 | Escrow/Payments | `_finalize_escrow_if_paid` change le statut en `RELEASED` et ajoute un event sans `commit`, laissant l’état volatil et incohérent entre workers. | Élevé (escrow jamais fermé officiellement) | Moyenne | P1 | Appeler `db.commit()` (ou confier la clôture à `execute_payout`) et écrire un test de régression sur l’event `CLOSED`.【F:app/services/payments.py†L280-L303】 |
| R5 | Ops | Scheduler APScheduler tourne par process (aucun lock), possible double expiration + contention DB sur multi-réplicas. | Moyen | Moyenne | P2 | Activer un flag `SCHEDULER_ENABLED`, externaliser vers job unique (Celery/cron) ou utiliser APScheduler `DistributedLock`.【F:app/main.py†L31-L45】【F:app/services/cron.py†L12-L33】 |

## I. Roadmap to MVP-ready
- P0 :
  - Corriger `require_scope` pour accepter des ensembles d’`ApiScope` et couvrir les scopes `sender/support` en tests AnyIO.【F:app/security.py†L83-L100】【F:tests/test_scopes.py†L7-L20】
  - Forcer la désactivation de `DEV_API_KEY` hors environnements de test et suivre son usage (audit + métrique).【F:app/config.py†L11-L63】【F:app/security.py†L35-L57】
  - Ajouter des entrées `AuditLog` (et éventuellement un modèle historique) lors des appels `/allowlist` et `/certified`, avec assertions de tests.【F:app/services/transactions.py†L34-L86】
- P1 :
  - Assurer la persistance de `_finalize_escrow_if_paid` (commit + audit éventuel), puis couvrir via test d’intégration escrow complet.【F:app/services/payments.py†L280-L303】
  - Étendre la couverture aux cas d’erreur PSP (double signature, timestamp invalide) via tests supplémentaires.【F:app/services/psp_webhooks.py†L20-L83】
- P2 :
  - Rendre le scheduler optionnel/configurable et documenter l’exécution unique (ex. via worker dédié).【F:app/main.py†L31-L45】
  - Industrialiser le monitoring (Prometheus exposé, Sentry DSN réel) et ajouter des dashboards sur les `AuditLog` critiques.【F:app/main.py†L47-L57】【F:app/services/escrow.py†L74-L248】

**Verdict : NO-GO tant que les garde-fous P0 (RBAC, clé legacy, audit allowlist/certif) ne sont pas traités.**
