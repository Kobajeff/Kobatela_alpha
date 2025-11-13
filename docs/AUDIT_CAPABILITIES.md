# Kobatela_alpha — Capability & Stability Audit (2025-11-13)

## A. Executive summary
- Forces :
  - RBAC par clé API avec scopes `ApiScope` et journalisation systématique des usages, couvrant la clé legacy et les clés persistées.【F:app/security.py†L31-L147】
  - Modélisation monétaire uniforme en `Numeric(18,2)` sur transactions, paiements et séquestres, garantissant l’absence de floats pour les montants critiques.【F:app/models/transaction.py†L20-L37】【F:app/models/payment.py†L21-L39】【F:app/models/escrow.py†L33-L55】
  - Parcours idempotents de bout en bout (dépôts, achats, paiements, webhooks) via helpers partagés et clés uniques, réduisant les doubles débits.【F:app/services/idempotency.py†L12-L50】【F:app/services/escrow.py†L101-L173】【F:app/services/payments.py†L84-L203】【F:app/services/psp_webhooks.py†L16-L95】
  - Pipeline preuves riche (validation EXIF/GPS, geofence haversine, auto-approbation) déclenchant les paiements tout en journalisant chaque étape.【F:app/services/proofs.py†L63-L214】
  - Lifespan FastAPI impose la présence du secret PSP, initialise la base et ne démarre le scheduler qu’avec un flag explicite, tout en exposant CORS/Prometheus/Sentry configurables.【F:app/main.py†L23-L78】【F:app/config.py†L21-L49】
- Risques :
  - Les routes `/allowlist`, `/certified` et `/transactions` n’imposent qu’une clé API générique : n’importe quel scope peut modifier la surface antifraude (RBAC manquant).【F:app/routers/transactions.py†L17-L43】【F:app/security.py†L130-L147】
  - La route `POST /spend` génère un Idempotency-Key par défaut basé sur (escrow, payee, montant) ; deux dépenses légitimes identiques sont bloquées comme doublons involontaires.【F:app/routers/spend.py†L95-L103】
  - `POST /payments/execute/{id}` n’invoque aucun post-traitement après l’envoi : un escrow payé manuellement ne repasse pas en `RELEASED` ni n’émet d’événement de clôture.【F:app/services/payments.py†L205-L278】
  - Les limites quotidiennes/totales d’`AllowedPayee` reposent sur un simple read-check-update sans verrou : deux requêtes concurrentes peuvent dépasser la limite avant le commit.【F:app/services/usage.py†L121-L236】
  - Les routes `/users` et `/alerts` restent accessibles à tout détenteur de clé (même `sender`), sans séparation de rôle pour ces opérations sensibles côté back-office.【F:app/routers/users.py†L11-L31】【F:app/routers/alerts.py†L11-L19】

Readiness score: **68 / 100** — NO-GO tant que le RBAC des routes transactions n’est pas resserré.

## B. Capability map (current, concrete)
### B.1 Feature coverage
| Feature | Implemented endpoints/modules | Status | Notes |
| --- | --- | --- | --- |
| Santé & métadonnées | `GET /health` → `health.healthcheck` | Implémenté | Ping JSON sans authentification pour monitoring basique.【F:app/routers/health.py†L4-L11】 |
| Gestion clés API | `POST/GET/DELETE /apikeys` | Implémenté | Création, lecture et révocation réservées au scope admin avec `AuditLog` et génération de clé unique.【F:app/routers/apikeys.py†L62-L173】 |
| Gestion utilisateurs | `POST /users`, `GET /users/{id}` | Implémenté (RBAC à renforcer) | CRUD minimal protégé par clé API générique ; aucun scope dédié n’empêche un compte `sender` d’appeler ces routes.【F:app/routers/users.py†L11-L31】 |
| Allowlist & certification | `/allowlist`, `/certified` | Implémenté (P0 RBAC) | Ajout/déduplication et certification avec audit trail, mais accessibles à toute clé valide.【F:app/routers/transactions.py†L27-L63】【F:app/services/transactions.py†L34-L86】 |
| Transactions restreintes | `POST/GET /transactions` | Implémenté | Création idempotente, alerting antifraude et audit complet.【F:app/routers/transactions.py†L66-L88】【F:app/services/transactions.py†L87-L140】 |
| Escrow lifecycle | `/escrows/*` | Implémenté | Création, dépôts idempotents, transitions client/provider, lecture directe ; dépend du scope `sender`.【F:app/routers/escrow.py†L12-L67】【F:app/services/escrow.py†L60-L248】 |
| Mandats d’usage | `/mandates`, `/mandates/cleanup` | Implémenté | Création auditée, anti-doublon SQL et cron d’expiration configuré par flag.【F:app/routers/mandates.py†L12-L31】【F:app/services/mandates.py†L68-L176】【F:app/main.py†L33-L45】 |
| Spend catalogues | `/spend/categories`, `/spend/merchants`, `/spend/allow` | Implémenté | Vérifications d’unicité et retour de statut clair pour la configuration catalogue.【F:app/routers/spend.py†L22-L42】【F:app/services/spend.py†L97-L185】 |
| Purchases conditionnels | `POST /spend/purchases` | Implémenté | Mandat actif requis, contrôles allowlist/certification et décrément atomique des plafonds.【F:app/routers/spend.py†L44-L51】【F:app/services/spend.py†L187-L341】 |
| Allowed payees & usage spend | `POST /spend/allowed`, `POST /spend` | Implémenté (améliorations à prévoir) | Gestion des payees avec limites + dépense idempotente, mais fallback Idempotency-Key perfectible et limites non verrouillées.【F:app/routers/spend.py†L53-L105】【F:app/services/usage.py†L121-L236】 |
| Preuves & milestones | `/proofs`, `/proofs/{id}/decision` | Implémenté | Validation photo, décisions, auto-approbation et clôture escrow via milestones payées.【F:app/routers/proofs.py†L12-L37】【F:app/services/proofs.py†L63-L320】 |
| Paiements & PSP | `/payments/execute/{id}`, `/psp/webhook` | Implémenté (post-traitement manuel manquant) | Exécution idempotente, audit `EXECUTE_PAYOUT`, webhooks HMAC/timestamp ; manque finalisation après paiement manuel.【F:app/routers/payments.py†L11-L21】【F:app/services/payments.py†L205-L278】【F:app/routers/psp.py†L20-L61】 |

### B.2 Supported end-to-end flows (today)
- Mandat diaspora → achat conditionnel : `/users` (création bénéficiaires) → `/mandates` (anti-doublon + audit) → `/spend/purchases` (consommation mandat et audit).【F:app/routers/users.py†L11-L31】【F:app/services/mandates.py†L91-L176】【F:app/services/spend.py†L257-L371】
- Escrow avec preuves photo : `/escrows` → `/escrows/{id}/deposit` (idempotent) → `/proofs` (validation photo) → paiement automatique puis clôture `CLOSED` lorsque tous les jalons sont payés.【F:app/routers/escrow.py†L12-L63】【F:app/services/escrow.py†L101-L248】【F:app/services/proofs.py†L139-L412】
- Paiement manuel + webhook PSP : `/payments/execute/{id}` (envoi idempotent + audit) → `/psp/webhook` (signature HMAC, `PAYMENT_SETTLED`/`FAILED`).【F:app/services/payments.py†L205-L277】【F:app/routers/psp.py†L20-L61】【F:app/services/psp_webhooks.py†L54-L145】

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request | Response | Codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | /health | `health.healthcheck`【F:app/routers/health.py†L4-L11】 | Aucune | - | - | `{status}` | 200 |
| POST | /users | `users.create_user`【F:app/routers/users.py†L14-L22】 | Clé API (`require_api_key`)【F:app/routers/users.py†L11-L31】 | Tous scopes | `UserCreate` | `UserRead` | 201 |
| GET | /users/{user_id} | `users.get_user`【F:app/routers/users.py†L25-L31】 | Clé API | Tous scopes | - | `UserRead` | 200/404 |
| POST | /allowlist | `transactions.add_to_allowlist`【F:app/routers/transactions.py†L27-L44】 | Clé API | Tous scopes (RBAC manquant) | `AllowlistCreate` | `{status}` | 201 |
| POST | /certified | `transactions.add_certification`【F:app/routers/transactions.py†L27-L63】 | Clé API | Tous scopes (RBAC manquant) | `CertificationCreate` | `{status}` | 201 |
| POST | /transactions | `transactions.post_transaction`【F:app/routers/transactions.py†L34-L43】 | Clé API | Tous scopes (RBAC manquant) | `TransactionCreate` + `Idempotency-Key?` | `TransactionRead` | 201 |
| GET | /transactions/{transaction_id} | `transactions.get_transaction`【F:app/routers/transactions.py†L46-L55】 | Clé API | Tous scopes | - | `TransactionRead` | 200/404 |
| POST | /escrows | `escrow.create_escrow`【F:app/routers/escrow.py†L20-L21】 | Clé API + `require_scope({sender})` | Sender/Admin | `EscrowCreate` | `EscrowRead` | 201 |
| POST | /escrows/{id}/deposit | `escrow.deposit`【F:app/routers/escrow.py†L25-L32】 | Clé API + scope sender | Sender/Admin | `EscrowDepositCreate` + `Idempotency-Key?` | `EscrowRead` | 200 |
| POST | /escrows/{id}/mark-delivered | `escrow.mark_delivered`【F:app/routers/escrow.py†L35-L37】 | Clé API + scope sender | Sender/Admin | `EscrowActionPayload` | `EscrowRead` | 200 |
| POST | /escrows/{id}/client-approve | `escrow.client_approve`【F:app/routers/escrow.py†L40-L45】 | Clé API + scope sender | Sender/Admin | `EscrowActionPayload?` | `EscrowRead` | 200 |
| POST | /escrows/{id}/client-reject | `escrow.client_reject`【F:app/routers/escrow.py†L49-L55】 | Clé API + scope sender | Sender/Admin | `EscrowActionPayload?` | `EscrowRead` | 200 |
| POST | /escrows/{id}/check-deadline | `escrow.check_deadline`【F:app/routers/escrow.py†L58-L60】 | Clé API + scope sender | Sender/Admin | - | `EscrowRead` | 200 |
| GET | /escrows/{id} | `escrow.read_escrow`【F:app/routers/escrow.py†L63-L67】 | Clé API + scope sender | Sender/Admin | - | `EscrowRead` | 200/404 |
| GET | /alerts | `alerts.list_alerts`【F:app/routers/alerts.py†L14-L19】 | Clé API | Tous scopes | Query `type?` | `list[AlertRead]` | 200 |
| POST | /mandates | `mandates.create_mandate`【F:app/routers/mandates.py†L20-L24】 | Clé API + scope sender | Sender/Admin | `UsageMandateCreate` | `UsageMandateRead` | 201 |
| POST | /mandates/cleanup | `mandates.cleanup_expired_mandates`【F:app/routers/mandates.py†L27-L32】 | Clé API + scope sender | Sender/Admin | - | `{expired}` | 202 |
| POST | /spend/categories | `spend.create_category`【F:app/routers/spend.py†L30-L32】 | Clé API + scope sender | Sender/Admin | `SpendCategoryCreate` | `SpendCategoryRead` | 201 |
| POST | /spend/merchants | `spend.create_merchant`【F:app/routers/spend.py†L35-L37】 | Clé API + scope sender | Sender/Admin | `MerchantCreate` | `MerchantRead` | 201 |
| POST | /spend/allow | `spend.allow_usage`【F:app/routers/spend.py†L40-L42】 | Clé API + scope sender | Sender/Admin | `AllowedUsageCreate` | `{status}` | 201 |
| POST | /spend/purchases | `spend.create_purchase`【F:app/routers/spend.py†L45-L51】 | Clé API + scope sender | Sender/Admin | `PurchaseCreate` + `Idempotency-Key?` | `PurchaseRead` | 201 |
| POST | /spend/allowed | `spend.add_allowed_payee`【F:app/routers/spend.py†L62-L79】 | Clé API + scope sender | Sender/Admin | `AddPayeeIn` | Dict payee | 201 |
| POST | /spend | `spend.spend`【F:app/routers/spend.py†L89-L103】 | Clé API + scope sender | Sender/Admin | `SpendIn` + `Idempotency-Key?` | Dict paiement | 200 |
| POST | /payments/execute/{payment_id} | `payments.execute_payment`【F:app/routers/payments.py†L18-L22】 | Clé API + scope sender | Sender/Admin | - | `PaymentRead` | 200/404 |
| POST | /proofs | `proofs.submit_proof`【F:app/routers/proofs.py†L19-L23】 | Clé API + scope sender | Sender/Admin | `ProofCreate` | `ProofRead` | 201 |
| POST | /proofs/{id}/decision | `proofs.decide_proof`【F:app/routers/proofs.py†L26-L37】 | Clé API + scope sender | Sender/Admin | `ProofDecision` | `ProofRead` | 200/400 |
| POST | /psp/webhook | `psp.psp_webhook`【F:app/routers/psp.py†L20-L61】 | Secret HMAC | PSP | JSON libre | `{ok,event_id}` | 200/401/503 |
| POST | /apikeys | `apikeys.create_api_key`【F:app/routers/apikeys.py†L62-L107】 | Clé API + scope admin | Admin | `CreateKeyIn` | `ApiKeyCreateOut` | 201 |
| GET | /apikeys/{id} | `apikeys.get_apikey`【F:app/routers/apikeys.py†L116-L128】 | Clé API + scope admin | Admin | - | `ApiKeyRead` | 200/404 |
| DELETE | /apikeys/{id} | `apikeys.revoke_apikey`【F:app/routers/apikeys.py†L131-L173】 | Clé API + scope admin | Admin | - | - | 204/404 |

## D. Data model & states
| Entity | Key fields & constraints | Notes |
| --- | --- | --- |
| User | `username`, `email`, `is_active` (unicité, FK transactions) | Relations vers transactions envoyées/reçues.【F:app/models/user.py†L10-L21】 |
| ApiKey | `prefix`, `key_hash`, `scope`, `is_active`, `expires_at` | Enum `ApiScope`, unicité `prefix`/`key_hash`, audit des usages.【F:app/models/api_key.py†L12-L31】【F:app/security.py†L107-L126】 |
| AuditLog | `actor`, `action`, `entity`, `entity_id`, `data_json`, `at` | Journal structuré horodaté (toutes mutations critiques).【F:app/models/audit.py†L10-L20】 |
| Alert | `type`, `message`, `payload_json` (index `created_at`) | Persistées via service dédié avec log warning.【F:app/models/alert.py†L8-L17】【F:app/services/alerts.py†L11-L17】 |
| Transaction | `sender_id`, `receiver_id`, `amount`, `status`, `idempotency_key` | `Numeric(18,2)`, index statut, FK utilisateurs.【F:app/models/transaction.py†L20-L37】 |
| AllowedRecipient | `owner_id`, `recipient_id` (unique) | Gère les allowlists antifraude.【F:app/models/allowlist.py†L7-L14】 |
| CertifiedAccount | `user_id` (unique), `level`, `certified_at` | Enum `CertificationLevel`, mise à jour auditée.【F:app/models/certified.py†L11-L25】【F:app/services/transactions.py†L63-L86】 |
| EscrowAgreement | `client_id`, `provider_id`, `amount_total`, `status`, `deadline_at` | `Numeric(18,2)`, contraintes montant positif et index statut/délais.【F:app/models/escrow.py†L19-L55】 |
| EscrowDeposit | `escrow_id`, `amount`, `idempotency_key` (unique) | Montants positifs, idempotence gérée par service.【F:app/models/escrow.py†L45-L55】【F:app/services/escrow.py†L101-L165】 |
| EscrowEvent | `escrow_id`, `kind`, `data_json`, `idempotency_key?` | Historique JSON horodaté des actions escrow.【F:app/models/escrow.py†L58-L69】 |
| Milestone | `escrow_id`, `idx`, `amount`, `status`, geofence | `Numeric(18,2)`, contraintes idx/amount > 0, geofence optionnelle en float.【F:app/models/milestone.py†L22-L47】 |
| Proof | `escrow_id`, `milestone_id`, `sha256`, `status`, `metadata` | `sha256` unique, métadonnées JSON, audit lors des transitions.【F:app/models/proof.py†L10-L24】【F:app/services/proofs.py†L139-L320】 |
| Payment | `escrow_id`, `milestone_id`, `amount`, `status`, `idempotency_key` | `Numeric(18,2)`, indices statut/idempotence, `psp_ref` unique.【F:app/models/payment.py†L21-L39】 |
| PSPWebhookEvent | `event_id` (unique), `kind`, `psp_ref`, `raw_json` | Permet l’idempotence des webhooks + timestamps reçus/traités.【F:app/models/psp_webhook.py†L10-L25】 |
| UsageMandate | `sender_id`, `beneficiary_id`, `total_amount`, `status`, `total_spent` | `Numeric(18,2)`, index de recherche active, transitions auditables.【F:app/models/usage_mandate.py†L30-L65】【F:app/services/mandates.py†L109-L176】 |
| AllowedPayee | `escrow_id`, `payee_ref`, limites quotidiennes/totales` | Contraintes de positivité et unicité (escrow, payee).【F:app/models/allowed_payee.py†L11-L32】 |
| SpendCategory & Merchant | `code`, `label` / `name`, `category_id`, `is_certified` | Unicité code/nom, relation `category→merchants`.【F:app/models/spend.py†L9-L35】 |
| Purchase | `sender_id`, `merchant_id`, `amount`, `status`, `idempotency_key` | Montant positif, idempotence, index statut/idempotency.【F:app/models/spend.py†L61-L83】 |

State machines :
- Escrow : `DRAFT` → `FUNDED` → `RELEASABLE` → `RELEASED/REFUNDED/CANCELLED` selon livraisons et décisions client.【F:app/models/escrow.py†L9-L55】【F:app/services/escrow.py†L168-L248】
- Milestone : `WAITING` → `PENDING_REVIEW/APPROVED` → `PAYING` → `PAID` ou `REJECTED`, enchaîné avec preuves et paiements.【F:app/models/milestone.py†L11-L47】【F:app/services/proofs.py†L172-L365】
- Payment : `PENDING` → `SENT` → `SETTLED` ou `ERROR`, déclenché par `execute_payout` puis webhooks PSP.【F:app/models/payment.py†L11-L39】【F:app/services/psp_webhooks.py†L85-L145】
- Proof : `PENDING` → `APPROVED/REJECTED` selon décision ou auto-validation photo.【F:app/models/proof.py†L10-L24】【F:app/services/proofs.py†L172-L320】
- UsageMandate : `ACTIVE` → `CONSUMED` ou `EXPIRED`, piloté par consommation atomique et cron d’expiration.【F:app/models/usage_mandate.py†L22-L65】【F:app/services/spend.py†L287-L340】【F:app/services/cron.py†L12-L33】

## E. Stability results
- `alembic upgrade head` appliqué sans erreur sur SQLite (chaîne linéaire jusqu’à `8b7e_add_api_keys`).【4e8410†L1-L12】
- `alembic current` et `alembic heads` confirment l’absence de drift (unique head).【edd032†L1-L4】【99fc45†L1-L3】
- `pytest -q` : 39 tests verts (1 avertissement Pydantic V2 sur `BaseModel.config`).【6eb611†L1-L9】
- Revue statique : RBAC manquant sur `/transactions`, Idempotency-Key par défaut trop permissif, absence de verrouillage concurrent sur `spend_to_allowed_payee`, post-traitement d’escrow manquant après paiement manuel.【F:app/routers/transactions.py†L17-L43】【F:app/routers/spend.py†L95-L103】【F:app/services/usage.py†L121-L236】【F:app/services/payments.py†L205-L278】

## F. Security & integrity
- AuthN/Z : `require_api_key` audite chaque appel, désactive la clé legacy hors dev/local et fournit une sentinelle admin lorsqu’elle est autorisée ; `require_scope` accepte bien un `set[ApiScope]` et valide l’appartenance ou le rôle admin.【F:app/security.py†L31-L147】
- Entrées strictes via Pydantic (montants >0, devise `USD|EUR`, validations mandat/usage/proof) limitant les entrées dangereuses côté SQL.【F:app/schemas/escrow.py†L10-L36】【F:app/schemas/mandates.py†L12-L43】【F:app/schemas/spend.py†L12-L78】【F:app/schemas/proof.py†L7-L33】【F:app/schemas/transaction.py†L11-L38】
- Pipeline preuves : validations EXIF/GPS et codes d’erreur dédiés avant mutation d’état ; auto-approbation journalisée et paiements déclenchés avec audit.【F:app/services/proofs.py†L63-L320】
- Paiements/PSP : signature HMAC SHA-256 + horodatage ±5 min, idempotence `event_id`, audit `PAYMENT_SETTLED/FAILED` et logs structurés.【F:app/services/psp_webhooks.py†L16-L145】【F:app/routers/psp.py†L29-L61】
- Audit : allowlist, certification, achats, dépenses usage, escrows, mandats, paiements et preuves génèrent des entrées `AuditLog` détaillées.【F:app/services/transactions.py†L34-L86】【F:app/services/spend.py†L342-L369】【F:app/services/usage.py†L205-L230】【F:app/services/escrow.py†L74-L248】【F:app/services/payments.py†L229-L259】
- Points durs restants : absence de scopes dédiés sur `/transactions` et `/users`, et défaut de verrouillage sur les limites `AllowedPayee` exposent des risques d’escalade ou de dépassement de plafond.【F:app/routers/transactions.py†L17-L43】【F:app/routers/users.py†L11-L31】【F:app/services/usage.py†L121-L236】

## G. Observability & ops
- Logging structuré via `setup_logging`, Prometheus (`/metrics`) et Sentry activables par configuration, avec CORS centralisé.【F:app/main.py†L56-L75】【F:app/core/logging.py†L10-L31】【F:app/config.py†L43-L49】
- Scheduler APScheduler protégé par `SCHEDULER_ENABLED` ; commentaire explicite sur l’exécution mono-runner, mais pas de verrou distribué intégré.【F:app/main.py†L33-L45】【F:app/config.py†L21-L28】
- Configuration `.env` gérée par `Settings`, secret PSP obligatoire au démarrage et moteurs SQL initialisés/fermés proprement.【F:app/main.py†L23-L52】【F:app/config.py†L32-L71】【F:app/db.py†L11-L73】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | AuthN/Z | `/allowlist`, `/certified`, `/transactions` accessibles à tout scope API → modification de la politique antifraude par une clé `sender`. | Critique (contournement antifraude) | Moyenne | P0 | Ajouter `require_scope({ApiScope.admin})` (ou support) aux routes transactions et compléter les tests RBAC.【F:app/routers/transactions.py†L17-L43】 |
| R2 | Usage spend | Fallback Idempotency-Key basé sur montant bloque deux dépenses identiques légitimes (même montant/payeé). | Élevé (blocage flux) | Élevée | P1 | Exiger une clé idempotence fournie par le client ou inclure un identifiant temporel unique dans la clé générée.【F:app/routers/spend.py†L95-L103】 |
| R3 | Paiements | Paiement manuel ne déclenche pas de clôture escrow ni d’event `CLOSED`. | Élevé (statut incohérent) | Moyenne | P1 | Appeler `_finalize_escrow_if_paid` ou `_handle_post_payment` après `execute_payout`, puis tester la chaîne complète.【F:app/services/payments.py†L205-L278】 |
| R4 | AllowedPayee | Contrôles limites (daily/total) non sérialisés : deux requêtes concurrentes peuvent dépasser les plafonds avant commit. | Élevé (dépassement autorisations) | Moyenne | P1 | Utiliser `SELECT ... FOR UPDATE` ou contraintes DB supplémentaires, et ajouter des tests de concurrence (e.g. via threads).【F:app/services/usage.py†L121-L236】 |
| R5 | Back-office | `/users` et `/alerts` accessibles à toute clé (même `sender`), absence de séparation back-office/support. | Moyen (surface d’administration exposée) | Moyenne | P2 | Introduire un scope `support`/`admin` sur ces routes et couvrir par tests d’accès négatifs.【F:app/routers/users.py†L11-L31】【F:app/routers/alerts.py†L11-L19】 |

## I. Roadmap to MVP-ready
- P0 :
  - Appliquer `require_scope({ApiScope.admin})` sur les routes transactions (allowlist/certified/transactions) et étendre les tests AnyIO pour confirmer le refus des clés `sender`.【F:app/routers/transactions.py†L17-L43】【F:tests/test_scopes.py†L7-L20】
- P1 :
  - Modifier `POST /spend` pour accepter une Idempotency-Key client obligatoire (ou enrichir la clé générée) et ajouter des tests d’acceptation pour dépenses répétées.【F:app/routers/spend.py†L95-L103】
  - Après `execute_payout`, ré-invoquer `_finalize_escrow_if_paid`/`_handle_post_payment` et écrire un test d’intégration couvrant la clôture via paiement manuel.【F:app/services/payments.py†L205-L319】
  - Protéger `spend_to_allowed_payee` par un verrou pessimiste ou une contrainte DB pour éviter les dépassements concurrents, avec test de charge minimal.【F:app/services/usage.py†L121-L236】
- P2 :
  - Restreindre `/users` et `/alerts` aux scopes `support/admin` et consigner ces accès pour audit back-office.【F:app/routers/users.py†L11-L31】【F:app/routers/alerts.py†L11-L19】
  - Documenter un processus de rotation du secret PSP (reload config) et exposer des métriques SLO sur `AuditLog` critiques.【F:app/routers/psp.py†L29-L61】【F:app/services/escrow.py†L74-L248】

**Verdict : NO-GO tant que le RBAC transactions n’est pas corrigé et que les flux spend/paiement ne sont pas durcis.**
