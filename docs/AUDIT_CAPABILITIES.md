# Kobatela_alpha — Capability & Stability Audit (2025-11-13)

## A. Executive summary
- ✅ Les dépendances `require_scope` sont branchées sur les routeurs métiers (escrows, spend, mandates, proofs, payments) et s'appuient sur une validation centralisée des scopes avec audit `API_KEY_USED`.【F:app/routers/escrow.py†L12-L63】【F:app/routers/spend.py†L17-L105】【F:app/security.py†L12-L70】
- ✅ Les flux monétaires (purchases, escrow deposits/payouts, usage payees) fonctionnent intégralement en `Decimal(18,2)` avec décrément atomique et journaux d'audit pour tracer chaque consommation de mandat.【F:app/models/spend.py†L64-L83】【F:app/services/spend.py†L187-L371】
- ✅ Le webhook PSP est durci par secret obligatoire au démarrage, signature HMAC + fenêtre temporelle et idempotence par `event_id` avec audit Payment.【F:app/main.py†L23-L45】【F:app/routers/psp.py†L20-L61】【F:app/services/psp_webhooks.py†L20-L114】
- ✅ Le cycle séquestre (création, dépôts, livraison, approbations/rejets) applique des audits systématiques et des événements chronologiques, garantissant une traçabilité complète.【F:app/services/escrow.py†L60-L250】
- ✅ Observabilité activable : CORS restreint, Prometheus/Sentry paramétrables et cron d'expiration des mandats piloté par APScheduler depuis le lifespan unique.【F:app/config.py†L19-L39】【F:app/main.py†L46-L69】【F:app/services/cron.py†L12-L33】
- ⚠️ Les clés API sont stockées en clair (`ApiKey.key`) et fournies par l'admin côté requête, exposant le secret en base et dans les journaux (P0).【F:app/models/api_key.py†L12-L31】【F:app/routers/apikeys.py†L24-L76】
- ⚠️ L'environnement par défaut est `dev`, ce qui laisse la clé legacy active si `KOB_ENV` n'est pas fixé (P0).【F:app/config.py†L11-L25】
- ⚠️ Les routes allowlist/certification/transactions n'imposent aucun scope spécifique : une simple clé `sender` peut gérer des fonctions quasi-admin (P1).【F:app/routers/transactions.py†L21-L88】【F:app/security.py†L54-L70】
- ⚠️ L'APScheduler embarqué dans FastAPI peut lancer des jobs concurrents ou se couper lors d'un redéploiement multi-pod (P2).【F:app/main.py†L23-L45】【F:app/services/cron.py†L12-L33】
- ⚠️ Le cycle de vie des API keys ne prévoit ni expiration ni rotation automatique malgré `last_used_at`, ce qui limite la gouvernance (P2).【F:app/models/api_key.py†L12-L31】【F:app/routers/apikeys.py†L24-L113】

Readiness score: **74 / 100** — exploitable pour un pilote restreint si la clé legacy est neutralisée et si la gestion des secrets API est renforcée.

## B. Capability map (current, concrete)
### B.1 Feature coverage
| Feature | Implemented endpoints/modules | Status | Notes |
| --- | --- | --- | --- |
| Santé API | `GET /health` | Implémenté | Ping simple pour monitoring externe.【F:app/routers/health.py†L4-L11】 |
| Gestion utilisateurs | `POST /users`, `GET /users/{id}` | Implémenté | CRUD minimal protégé par clé API, pas de différenciation de scope.【F:app/routers/users.py†L11-L31】 |
| Alertes opérationnelles | `GET /alerts` | Implémenté | Consultation filtrée, utilisée par les transactions pour remonter les tentatives interdites.【F:app/routers/alerts.py†L11-L19】【F:app/services/transactions.py†L34-L86】 |
| Gouvernance API Keys | `POST/GET/DELETE /apikeys/{id}` | Partiel | CRUD admin avec audit, mais stockage en clair et pas de génération côté serveur.【F:app/routers/apikeys.py†L24-L113】 |
| Escrow lifecycle | `/escrows/*` | Implémenté | Création, dépôt idempotent, transitions client/fournisseur et audits associés.【F:app/routers/escrow.py†L12-L63】【F:app/services/escrow.py†L60-L250】 |
| Allowlist & certifications | `/allowlist`, `/certified` | Implémenté | Ajout/déduplication et alertes, sans contrôle de scope dédié.【F:app/routers/transactions.py†L27-L64】 |
| Transactions restreintes | `POST/GET /transactions` | Implémenté | Idempotence par header + audit, accessible à toute clé active.【F:app/routers/transactions.py†L66-L88】【F:app/services/transactions.py†L25-L96】 |
| Mandats d'usage | `/mandates`, cron `close_expired_mandates` | Implémenté | Anti-doublon DB + audit création/expiration, job horaire pour l'expiration.【F:app/routers/mandates.py†L12-L27】【F:app/services/mandates.py†L68-L176】 |
| Spend & merchants | `/spend/categories`, `/spend/merchants`, `/spend/allow` | Implémenté | Création certifiée avec contrôles d'unicité et journaux.【F:app/routers/spend.py†L17-L74】【F:app/services/spend.py†L97-L171】 |
| Purchases conditionnels | `POST /spend/purchases` | Implémenté | Vérifie mandat actif, allowlist/certification, update atomique et audit.【F:app/routers/spend.py†L40-L46】【F:app/services/spend.py†L187-L371】 |
| Usage payees & payouts | `POST /spend` | Implémenté | Limites quotidiennes/totales, exécution idempotente et audit Payment.【F:app/routers/spend.py†L77-L105】【F:app/services/usage.py†L80-L236】 |
| Preuves & géofence | `/proofs`, `/proofs/{id}/decision` | Implémenté | Validation EXIF/GPS, auto-approbation et paiements déclenchés selon statut.【F:app/routers/proofs.py†L11-L33】【F:app/services/proofs.py†L25-L214】 |
| Paiements & webhooks | `/payments/execute/{id}`, `/psp/webhook` | Implémenté | Payouts idempotents + webhooks authentifiés qui mettent à jour le statut et auditent Payment.【F:app/routers/payments.py†L10-L17】【F:app/routers/psp.py†L20-L61】【F:app/services/psp_webhooks.py†L54-L114】 |

### B.2 Supported end-to-end flows (today)
- Provision d'accès : clé admin → `POST /apikeys` → appel Bearer ou `X-API-Key` sur les routes métiers protégées par scope.【F:app/routers/apikeys.py†L24-L76】【F:app/security.py†L12-L70】
- Mandat diaspora → achat : `POST /users` → `POST /mandates` (anti-doublon) → `POST /spend/purchases` (décrément atomique + audit).【F:app/routers/users.py†L11-L31】【F:app/routers/mandates.py†L12-L27】【F:app/services/spend.py†L187-L371】
- Séquestre à règlement : `POST /escrows` → `/escrows/{id}/deposit` (idempotent) → `/proofs` → `POST /payments/execute/{id}` + webhook HMAC pour SETTLED/ERROR.【F:app/routers/escrow.py†L12-L33】【F:app/services/proofs.py†L139-L214】【F:app/services/psp_webhooks.py†L54-L114】
- Usage payee : `POST /spend/allowed` → `POST /spend` → audit Payment + mise à jour des limites journalières/totales.【F:app/routers/spend.py†L49-L105】【F:app/services/usage.py†L80-L236】

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request | Response | Codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | /health | `health.healthcheck` | Aucun | n/a | – | `{status}` | 200【F:app/routers/health.py†L4-L11】 |
| POST | /users | `users.create_user` | API key | Tous scopes | `UserCreate` | `UserRead` | 201【F:app/routers/users.py†L11-L23】 |
| GET | /users/{id} | `users.get_user` | API key | Tous scopes | Path ID | `UserRead` | 200/404【F:app/routers/users.py†L25-L31】 |
| GET | /alerts | `alerts.list_alerts` | API key | Tous scopes | Query `type` | `list[AlertRead]` | 200【F:app/routers/alerts.py†L11-L19】 |
| POST | /apikeys | `apikeys.create_apikey` | API key | Admin | `ApiKeyCreate` | `ApiKeyRead` | 201/400【F:app/routers/apikeys.py†L24-L76】 |
| GET | /apikeys/{id} | `apikeys.get_apikey` | API key | Admin | Path ID | `ApiKeyRead` | 200/404【F:app/routers/apikeys.py†L78-L94】 |
| DELETE | /apikeys/{id} | `apikeys.revoke_apikey` | API key | Admin | Path ID | – | 204/404【F:app/routers/apikeys.py†L96-L113】 |
| POST | /escrows | `escrow.create_escrow` | API key | Sender/Admin | `EscrowCreate` | `EscrowRead` | 201【F:app/routers/escrow.py†L12-L19】 |
| POST | /escrows/{id}/deposit | `escrow.deposit` | API key | Sender/Admin | `EscrowDepositCreate` + `Idempotency-Key` | `EscrowRead` | 200/409【F:app/routers/escrow.py†L20-L33】 |
| POST | /escrows/{id}/mark-delivered | `escrow.mark_delivered` | API key | Sender/Admin | `EscrowActionPayload` | `EscrowRead` | 200【F:app/routers/escrow.py†L30-L33】 |
| POST | /escrows/{id}/client-approve | `escrow.client_approve` | API key | Sender/Admin | Body optionnel | `EscrowRead` | 200【F:app/routers/escrow.py†L35-L41】 |
| POST | /escrows/{id}/client-reject | `escrow.client_reject` | API key | Sender/Admin | Body optionnel | `EscrowRead` | 200【F:app/routers/escrow.py†L44-L50】 |
| POST | /escrows/{id}/check-deadline | `escrow.check_deadline` | API key | Sender/Admin | Path ID | `EscrowRead` | 200【F:app/routers/escrow.py†L53-L55】 |
| GET | /escrows/{id} | `escrow.read_escrow` | API key | Sender/Admin | Path ID | `EscrowRead` | 200/404【F:app/routers/escrow.py†L58-L63】 |
| POST | /allowlist | `transactions.add_to_allowlist` | API key | Tous scopes | `AllowlistCreate` | `{status}` | 201/200【F:app/routers/transactions.py†L27-L44】 |
| POST | /certified | `transactions.add_certification` | API key | Tous scopes | `CertificationCreate` | `{status}` | 201/200【F:app/routers/transactions.py†L46-L64】 |
| POST | /transactions | `transactions.post_transaction` | API key | Tous scopes | `TransactionCreate` + `Idempotency-Key` | `TransactionRead` | 201/409【F:app/routers/transactions.py†L66-L75】 |
| GET | /transactions/{id} | `transactions.get_transaction` | API key | Tous scopes | Path ID | `TransactionRead` | 200/404【F:app/routers/transactions.py†L78-L88】 |
| POST | /mandates | `mandates.create_mandate` | API key | Sender/Admin | `UsageMandateCreate` | `UsageMandateRead` | 201【F:app/routers/mandates.py†L12-L19】 |
| POST | /mandates/cleanup | `mandates.cleanup_expired_mandates` | API key | Sender/Admin | – | `{expired}` | 202【F:app/routers/mandates.py†L22-L27】 |
| POST | /spend/categories | `spend.create_category` | API key | Sender/Admin | `SpendCategoryCreate` | `SpendCategoryRead` | 201/400【F:app/routers/spend.py†L25-L27】 |
| POST | /spend/merchants | `spend.create_merchant` | API key | Sender/Admin | `MerchantCreate` | `MerchantRead` | 201/400/404【F:app/routers/spend.py†L30-L32】 |
| POST | /spend/allow | `spend.allow_usage` | API key | Sender/Admin | `AllowedUsageCreate` | `{status}` | 201/200/400/404【F:app/routers/spend.py†L35-L37】 |
| POST | /spend/purchases | `spend.create_purchase` | API key | Sender/Admin | `PurchaseCreate` + `Idempotency-Key` | `PurchaseRead` | 201/403/409【F:app/routers/spend.py†L40-L46】 |
| POST | /spend/allowed | `spend.add_allowed_payee` | API key | Sender/Admin | `AddPayeeIn` | Payee dict | 201/409【F:app/routers/spend.py†L49-L74】 |
| POST | /spend | `spend.spend` | API key | Sender/Admin | `SpendIn` + `Idempotency-Key` | Paiement dict | 200/400/403/409【F:app/routers/spend.py†L77-L105】 |
| POST | /proofs | `proofs.submit_proof` | API key | Sender/Admin | `ProofCreate` | `ProofRead` | 201/409/422【F:app/routers/proofs.py†L11-L24】 |
| POST | /proofs/{id}/decision | `proofs.decide_proof` | API key | Sender/Admin | `ProofDecision` | `ProofRead` | 200/400【F:app/routers/proofs.py†L26-L33】 |
| POST | /payments/execute/{id} | `payments.execute_payment` | API key | Sender/Admin | Path ID | `PaymentRead` | 200/404/409【F:app/routers/payments.py†L10-L17】 |
| POST | /psp/webhook | `psp.psp_webhook` | Secret PSP | n/a | JSON + headers | Ack dict | 200/401/503【F:app/routers/psp.py†L20-L61】 |

## D. Data model & states
| Entity | Key fields | Constraints / Indexes | Notes |
| --- | --- | --- | --- |
| ApiKey | `name`, `key`, `scope`, `is_active`, `last_used_at` | Unicité nom + clé, enum `apiscope` | Stockage en clair, audit usage via security.【F:app/models/api_key.py†L12-L31】【F:app/security.py†L34-L66】 |
| AuditLog | `actor`, `action`, `entity`, `entity_id`, `data_json`, `at` | Dates TZ | Centralise les traces de mandats, paiements, escrows, clés.【F:app/models/audit.py†L1-L18】【F:app/services/usage.py†L180-L233】 |
| User | `username`, `email`, `is_active` | Unicité + relations transactions | Pivot des mandats et transactions.【F:app/models/user.py†L1-L25】 |
| Alert | `type`, `message`, `payload_json` | Index type/date | Déclenché lors d'actions interdites.【F:app/models/alert.py†L1-L20】【F:app/services/transactions.py†L34-L86】 |
| UsageMandate | `sender_id`, `beneficiary_id`, `total_amount`, `status`, `total_spent` | Check ≥0, index lookup, unique actif (migration) | Consommation atomique et expiration cron.【F:app/models/usage_mandate.py†L22-L66】【F:alembic/versions/7a4c_unique_active_mandate.py†L1-L19】 |
| AllowedPayee | `escrow_id`, `payee_ref`, limites | Unique `(escrow_id,payee_ref)`, checks | Limites quotidiennes/totales sur usage payee.【F:app/models/allowed_payee.py†L1-L26】 |
| SpendCategory | `code`, `label` | Code unique | Lié aux merchants et allowed usage.【F:app/models/spend.py†L8-L21】 |
| Merchant | `name`, `category_id`, `is_certified` | Nom unique + index | Conditionne l'accès aux achats conditionnels.【F:app/models/spend.py†L24-L40】 |
| AllowedUsage | `owner_id`, `merchant_id/category_id` | Contrainte XOR + unicités | Règles supplémentaires pour purchases.【F:app/models/spend.py†L42-L53】 |
| Purchase | `sender_id`, `merchant_id`, `amount`, `status`, `idempotency_key` | Check >0, index statut | Montants en Decimal + idempotence clé.【F:app/models/spend.py†L64-L83】 |
| EscrowAgreement | `client_id`, `provider_id`, `amount_total`, `status`, `deadline_at` | Checks + index statut/échéance | Source des dépôts et paiements séquestrés.【F:app/models/escrow.py†L8-L33】 |
| EscrowDeposit | `escrow_id`, `amount`, `idempotency_key` | Check >0, clé unique | Empêche doubles dépôts.【F:app/models/escrow.py†L42-L52】 |
| EscrowEvent | `escrow_id`, `kind`, `data_json`, `idempotency_key` | Index kind/idempotence | Timeline auditable.【F:app/models/escrow.py†L54-L69】 |
| Milestone | `escrow_id`, `idx`, `amount`, `geofence_*`, `status` | Unicité `(escrow, idx)`, checks géofence | Support EXIF/GPS, montants en Decimal.【F:app/models/milestone.py†L1-L35】 |
| Proof | `escrow_id`, `milestone_id`, `sha256`, `status` | Hash unique | Pièces justificatives stockées avec métadonnées.【F:app/models/proof.py†L1-L24】 |
| Payment | `escrow_id`, `milestone_id`, `amount`, `status`, `psp_ref` | Checks + index statut/idempotence | Settlements via webhook + audit.【F:app/models/payment.py†L1-L33】 |
| Transaction | `sender_id`, `receiver_id`, `amount`, `status`, `idempotency_key` | Check >0, index statut | Virements restreints idempotents.【F:app/models/transaction.py†L1-L37】 |
| PSPWebhookEvent | `event_id`, `psp_ref`, `kind`, `processed_at` | Unique event_id | Idempotence de traitement PSP.【F:app/models/psp_webhook.py†L1-L21】 |

**State machines**
- `EscrowStatus` : DRAFT → FUNDED → RELEASABLE → RELEASED/REFUNDED/CANCELLED, chaque transition étant auditée via `_audit` et `EscrowEvent`.【F:app/models/escrow.py†L8-L33】【F:app/services/escrow.py†L60-L250】
- `UsageMandateStatus` : ACTIVE → CONSUMED (consommation atomique) ou EXPIRED (cron/job) avec audits associés.【F:app/models/usage_mandate.py†L22-L66】【F:app/services/spend.py†L287-L355】【F:app/services/cron.py†L12-L33】
- `PaymentStatus` : PENDING → SENT → SETTLED/ERROR selon exécution/PSP, avec audit PSP dédié.【F:app/models/payment.py†L1-L31】【F:app/services/psp_webhooks.py†L54-L114】
- `MilestoneStatus` : WAITING → PENDING_REVIEW/APPROVED → PAYING/PAID après preuve et paiement.【F:app/models/milestone.py†L11-L35】【F:app/services/proofs.py†L139-L214】

## E. Stability results
- `alembic upgrade head` : réussite, 7 révisions appliquées en chaîne SQLite.【b1ca76†L1-L10】
- `alembic current` : tête unique `7a4c_unique_active_mandate` confirmée.【1838ed†L1-L4】
- `alembic heads` : aucune branche divergente détectée.【0c1c56†L1-L2】
- `pytest -q` : 33 tests réussis, 1 avertissement Pydantic (config class-based).【b75f3a†L1-L9】
- Revue statique : toutes les sessions DB sont injectées par dépendance, pas de blocage async, logging centralisé via `app/core/logging`.【F:app/db.py†L1-L109】【F:app/core/logging.py†L1-L27】
- Idempotence : helpers partagés pour dépôts, paiements, achats et webhooks empêchent les doublons même en conditions concurrentes.【F:app/services/idempotency.py†L10-L41】【F:app/services/escrow.py†L101-L165】【F:app/services/spend.py†L287-L339】【F:app/services/psp_webhooks.py†L54-L114】

## F. Security & integrity
- Authentification : API key via header Bearer ou `X-API-Key`, clé legacy interdite hors dev, mise à jour `last_used_at` et audit à chaque appel.【F:app/security.py†L12-L66】
- Autorisation : scopes `sender/support/admin` imposés sur les routeurs métiers, mais certaines routes (allowlist, transactions) restent accessibles à n'importe quel scope valide.【F:app/routers/spend.py†L17-L105】【F:app/routers/transactions.py†L21-L88】
- Validation entrées : schémas Pydantic stricts, contrôles sur merchants/categories, limites de mandat et usage payee, géofence/Haversine sur preuves photo.【F:app/services/spend.py†L97-L371】【F:app/services/proofs.py†L25-L160】
- Secrets : `psp_webhook_secret` obligatoire pour démarrer, `SECRET_KEY` configurable, mais pas de hashage pour les clés API persistées.【F:app/main.py†L23-L45】【F:app/models/api_key.py†L12-L24】
- Audit : `AuditLog` alimenté pour mandats, achats, paiements, preuves, API keys ; webhooks PSP journalisent SETTLED/FAILED.【F:app/services/usage.py†L180-L233】【F:app/services/psp_webhooks.py†L73-L114】
- Idempotence : `get_existing_by_key` appliqué aux dépôts, transactions, paiements et usage payees pour éviter les doubles exécutions.【F:app/services/idempotency.py†L10-L41】【F:app/services/escrow.py†L101-L165】

## G. Observability & ops
- Lifespan unique : initialisation moteur SQL, démarrage/arrêt du scheduler et fermeture propre du pool lors du shutdown.【F:app/main.py†L23-L45】【F:app/db.py†L1-L109】
- CORS & métriques : origines configurables, middleware Prometheus activable, route `/metrics` exposée lorsque `PROMETHEUS_ENABLED`.【F:app/config.py†L19-L39】【F:app/main.py†L46-L69】
- Logging : configuration structurée via `app/core/logging`, extra context sur événements critiques (transactions, usage, webhooks).【F:app/core/logging.py†L1-L27】【F:app/services/transactions.py†L25-L96】
- Cron : job `expire_mandates_once` horaire ; absence de job store partagé impose un run unique ou un orchestrateur externe.【F:app/main.py†L33-L40】【F:app/services/cron.py†L12-L33】
- Déploiement : dépendances Python explicites, pas de scripts d'orchestration fournis ; `.env` requis pour base de données et secrets.【F:requirements.txt†L1-L14】【F:app/config.py†L19-L39】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Auth | Clé API stockée en clair et fournie par l'admin → compromission totale en cas de fuite DB | Critique | Moyen | **P0** | Stocker uniquement un hash HMAC/prefix, générer la clé côté serveur et ne jamais la réafficher après création.【F:app/models/api_key.py†L12-L24】【F:app/routers/apikeys.py†L24-L76】 |
| R2 | Config | `ENV` par défaut = `dev` garde la clé legacy active si oubli d'env var | Critique | Moyen | **P0** | Forcer `ENV` explicite au démarrage (raise sinon) ou rendre `DEV_API_KEY_ALLOWED` configurable par env séparé.【F:app/config.py†L11-L25】 |
| R3 | AuthZ | Routes allowlist/transactions manipulables par un scope `sender` | Élevé | Élevé | **P1** | Introduire `require_scope("support")` ou `require_scope("admin")` selon la criticité pour ces routes.【F:app/routers/transactions.py†L21-L88】【F:app/security.py†L54-L70】 |
| R4 | Ops | Cron APScheduler in-memory → jobs dupliqués ou manqués en multi-instance | Moyen | Moyen | **P2** | Déporter vers worker dédié ou job store persistant (Redis/DB) et activer un lock de leadership.【F:app/main.py†L33-L40】【F:app/services/cron.py†L12-L33】 |
| R5 | Gouvernance clés | Pas d'expiration/rotation automatique des API keys | Moyen | Moyen | **P2** | Ajouter un champ `expires_at` exploité et une tâche qui désactive les clés périmées + endpoint de rotation.【F:app/models/api_key.py†L12-L31】【F:app/routers/apikeys.py†L24-L113】 |

## I. Roadmap to MVP-ready
- **P0** :
  - Chiffrer/hasher les clés API persistées et générer les secrets côté backend (plus d'envoi en clair).【F:app/models/api_key.py†L12-L24】
  - Bloquer l'exécution si `KOB_ENV` n'est pas positionné à `staging/prod` et documenter la procédure de distribution des clés.【F:app/config.py†L11-L25】
- **P1** :
  - Appliquer `require_scope` adapté aux routes transactions/allowlist/certification et ajouter des tests RBAC (clé sender doit échouer).【F:app/routers/transactions.py†L21-L88】【F:tests/test_scopes.py†L1-L20】
  - Etendre la gestion des API keys : endpoints de liste, expiration, audit complet (création/révocation/usage).【F:app/routers/apikeys.py†L24-L113】
- **P2** :
  - Externaliser la planification (APS cheduleur dédié) ou ajouter un verrou de leader pour `expire_mandates_once`.【F:app/services/cron.py†L12-L33】
  - Documenter `/metrics` et intégrer un pipeline de logs/alerting (Sentry DSN, dashboards Prometheus).【F:app/main.py†L46-L69】

## Verification evidence
```text
$ alembic current
7a4c_unique_active_mandate (head)
```
【1838ed†L1-L4】

```text
$ alembic heads
7a4c_unique_active_mandate (head)
```
【0c1c56†L1-L2】

```text
$ pytest -q
33 passed, 1 warning in 1.72s
```
【b75f3a†L1-L9】

```text
$ rg "Float" app/models
app/models/milestone.py:5:... Float ...
app/models/milestone.py:42-44 geofence_* en Float
```
【2ad870†L1-L6】

**Verdict : NO-GO** — exiger le hashage/rotation des clés API et la neutralisation explicite de la clé legacy avant exposition à des utilisateurs externes.
