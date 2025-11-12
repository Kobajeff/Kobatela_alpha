# Kobatela_alpha — Capability & Stability Audit (2025-11-12)

## A. Executive summary
- ✅ Gestion multi-clés API livrée : stockage HMAC salé, scopes (`sender/support/admin`), génération administrée et compatibilité legacy pour les tests.【F:app/models/api_key.py†L12-L31】【F:app/utils/apikey.py†L16-L45】【F:app/routers/apikeys.py†L18-L49】【F:app/security.py†L13-L47】
- ✅ Démarrage durci via lifespan unique : secret PSP obligatoire, moteur SQL initialisé, cron d’expiration et middleware CORS/Prometheus/Sentry configurables par settings.【F:app/main.py†L23-L71】【F:app/config.py†L11-L25】【F:app/services/cron.py†L12-L33】
- ✅ Mandats d’usage blindés par index partiel unique, garde applicative et décrément atomique audité lors des dépenses conditionnelles.【F:alembic/versions/7a4c_unique_active_mandate.py†L1-L19】【F:app/services/mandates.py†L68-L176】【F:app/services/spend.py†L34-L371】
- ✅ Flux séquestre → preuve → paiement 100 % idempotents avec journal d’audit et garde sur soldes, couvrant dépôts, milestones et webhooks PSP.【F:app/services/escrow.py†L60-L250】【F:app/services/proofs.py†L45-L214】【F:app/services/payments.py†L20-L214】【F:app/services/idempotency.py†L10-L41】
- ✅ Chaîne Alembic linéaire et 31 tests verts assurant la non-régression fonctionnelle actuelle.【39bb0a†L1-L8】【d52c0a†L1-L4】【74d9f1†L1-L2】【33c257†L1-L2】
- ⚠️ `DEV_API_KEY` activé par défaut et accepté comme passe-partout, exposant toute l’API si le secret fuite (P0).【F:app/config.py†L11-L25】【F:app/utils/apikey.py†L31-L45】
- ⚠️ Les scopes ne sont pas appliqués sur les routes métier : toute clé non legacy obtient un accès complet (P1).【F:app/security.py†L35-L47】【F:app/routers/users.py†L11-L31】
- ⚠️ Création de clés API sans audit ni mise à jour de `last_used_at`, limitant la traçabilité et la détection d’abus (P1).【F:app/models/api_key.py†L18-L31】【F:app/routers/apikeys.py†L24-L49】
- ⚠️ Cron APScheduler dépend de chaque process FastAPI (pas de persistance, exécution concurrente possible), risque de dérive si plusieurs pods tournent (P2).【F:app/main.py†L23-L45】【F:app/services/cron.py†L12-L33】
- ⚠️ Aucune route publique pour révoquer/désactiver une clé API malgré le champ `is_active` (opération manuelle requise) (P2).【F:app/models/api_key.py†L18-L31】【F:app/routers/apikeys.py†L18-L49】

Readiness score: **78 / 100** — prêt pour un pilote fermé si la clé legacy est neutralisée et si le RBAC par scope est appliqué.

## B. Capability map (current, concrete)
### B.1 Feature coverage
| Feature | Implemented endpoints/modules | Status | Notes |
| --- | --- | --- | --- |
| Santé & métadonnées | `GET /health` → `health.healthcheck` | Implémenté | Ping synchrone pour monitoring basique.【F:app/routers/health.py†L4-L11】 |
| Gestion utilisateurs | `POST /users`, `GET /users/{id}` | Implémenté | CRUD minimal protégé par clé API, sans scopes différenciés.【F:app/routers/users.py†L11-L31】 |
| Alertes opérationnelles | `GET /alerts` | Implémenté | Filtre SQL simple, utilisé par la couche transactionnelle.【F:app/routers/alerts.py†L11-L19】【F:app/services/transactions.py†L34-L58】 |
| Gestion clés API | `POST /apikeys` (scope admin) | Implémenté | Génère clé HMAC, scope assigné, active par défaut, pas encore de révocation publique.【F:app/routers/apikeys.py†L18-L49】【F:app/security.py†L35-L47】 |
| Escrow lifecycle | `/escrows/*` | Implémenté | Création, dépôt idempotent, transitions client/pro fournisseur auditées.【F:app/routers/escrow.py†L12-L63】【F:app/services/escrow.py†L60-L250】 |
| Allowlist & certification | `/allowlist`, `/certified` | Implémenté | Déduplication et alertes en cas de tentative non autorisée.【F:app/routers/transactions.py†L27-L64】【F:app/services/transactions.py†L34-L86】 |
| Transactions restreintes | `POST /transactions` | Implémenté | Idempotency-Key respecté et audit systématique.【F:app/routers/transactions.py†L66-L75】【F:app/services/transactions.py†L25-L96】 |
| Mandats d’usage | `/mandates`, cron d’expiration | Implémenté | Création contrôlée, anti-doublon, expiration auditée manuellement ou via job.【F:app/routers/mandates.py†L12-L27】【F:app/services/mandates.py†L68-L176】 |
| Spend categories & merchants | `/spend/categories`, `/spend/merchants` | Implémenté | CRUD + vérifications d’unicité et logs.【F:app/routers/spend.py†L25-L37】【F:app/services/spend.py†L97-L171】 |
| Purchases conditionnels | `POST /spend/purchases` | Implémenté | Vérifie mandat actif, allowlist/certification, décrément atomique.【F:app/routers/spend.py†L40-L46】【F:app/services/spend.py†L187-L371】 |
| Usage payees & payouts | `/spend/allowed`, `/spend` | Implémenté | Limites quotidiennes/totales, idempotence et audit sur paiements usage.【F:app/routers/spend.py†L49-L105】【F:app/services/usage.py†L23-L236】 |
| Proofs & géofence | `/proofs`, `/proofs/{id}/decision` | Implémenté | Validation EXIF/GPS, auto-approbation + paiements idempotents.【F:app/routers/proofs.py†L11-L33】【F:app/services/proofs.py†L45-L214】 |
| Paiements sortants & webhooks | `/payments/execute/{id}`, `/psp/webhook` | Implémenté | Exécution idempotente, webhooks HMAC, mise à jour statut + audit.【F:app/routers/payments.py†L10-L17】【F:app/routers/psp.py†L20-L61】【F:app/services/psp_webhooks.py†L20-L145】 |

### B.2 Supported end-to-end flows (today)
- Cycle API interne : clé admin → `/apikeys` → utilisation Bearer sur routes métiers (legacy acceptée en QA).【F:app/routers/apikeys.py†L24-L49】【F:app/utils/apikey.py†L31-L45】
- Mandat diaspora → achat : `/users` → `/mandates` (anti-doublon) → `/spend/purchases` (décrément atomique + audit).【F:app/routers/users.py†L11-L31】【F:app/routers/mandates.py†L12-L27】【F:app/services/spend.py†L187-L371】
- Escrow à preuves : `/escrows` → dépôt idempotent → `/proofs` → paiements automatisés et clôture escrow.【F:app/routers/escrow.py†L12-L63】【F:app/services/escrow.py†L60-L250】【F:app/services/proofs.py†L139-L214】
- Paiement PSP : `/payments/execute/{id}` → webhook signé qui settle/erreur + audit Payment.【F:app/routers/payments.py†L10-L17】【F:app/services/psp_webhooks.py†L20-L145】

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request | Response | Codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | /health | `health.healthcheck` | Aucun | n/a | – | `{status}` | 200【F:app/routers/health.py†L4-L11】 |
| POST | /users | `users.create_user` | API key | Tous scopes | `UserCreate` | `UserRead` | 201【F:app/routers/users.py†L11-L23】 |
| GET | /users/{id} | `users.get_user` | API key | Tous scopes | Path ID | `UserRead` | 200/404【F:app/routers/users.py†L25-L31】 |
| GET | /alerts | `alerts.list_alerts` | API key | Tous scopes | Query `type` | `list[AlertRead]` | 200【F:app/routers/alerts.py†L11-L19】 |
| POST | /apikeys | `apikeys.create_api_key` | API key | Admin | `CreateKeyIn` | `{key,prefix,scope}` | 201【F:app/routers/apikeys.py†L24-L49】 |
| POST | /escrows | `escrow.create_escrow` | API key | Tous scopes | `EscrowCreate` | `EscrowRead` | 201【F:app/routers/escrow.py†L12-L17】 |
| POST | /escrows/{id}/deposit | `escrow.deposit` | API key | Tous scopes | `EscrowDepositCreate` + `Idempotency-Key` | `EscrowRead` | 200/409【F:app/routers/escrow.py†L20-L27】 |
| POST | /escrows/{id}/mark-delivered | `escrow.mark_delivered` | API key | Tous scopes | `EscrowActionPayload` | `EscrowRead` | 200【F:app/routers/escrow.py†L30-L33】 |
| POST | /escrows/{id}/client-approve | `escrow.client_approve` | API key | Tous scopes | Body optionnel | `EscrowRead` | 200【F:app/routers/escrow.py†L35-L41】 |
| POST | /escrows/{id}/client-reject | `escrow.client_reject` | API key | Tous scopes | Body optionnel | `EscrowRead` | 200【F:app/routers/escrow.py†L44-L50】 |
| POST | /escrows/{id}/check-deadline | `escrow.check_deadline` | API key | Tous scopes | Path ID | `EscrowRead` | 200【F:app/routers/escrow.py†L53-L55】 |
| GET | /escrows/{id} | `escrow.read_escrow` | API key | Tous scopes | Path ID | `EscrowRead` | 200/404【F:app/routers/escrow.py†L58-L63】 |
| POST | /allowlist | `transactions.add_to_allowlist` | API key | Tous scopes | `AllowlistCreate` | Statut dict | 201/200【F:app/routers/transactions.py†L27-L44】 |
| POST | /certified | `transactions.add_certification` | API key | Tous scopes | `CertificationCreate` | Statut dict | 201/200【F:app/routers/transactions.py†L46-L64】 |
| POST | /transactions | `transactions.post_transaction` | API key | Tous scopes | `TransactionCreate` + `Idempotency-Key` | `TransactionRead` | 201/409【F:app/routers/transactions.py†L66-L75】 |
| GET | /transactions/{id} | `transactions.get_transaction` | API key | Tous scopes | Path ID | `TransactionRead` | 200/404【F:app/routers/transactions.py†L78-L88】 |
| POST | /mandates | `mandates.create_mandate` | API key | Tous scopes | `UsageMandateCreate` | `UsageMandateRead` | 201【F:app/routers/mandates.py†L12-L19】 |
| POST | /mandates/cleanup | `mandates.cleanup_expired_mandates` | API key | Tous scopes | – | `{expired}` | 202【F:app/routers/mandates.py†L22-L27】 |
| POST | /spend/categories | `spend.create_category` | API key | Tous scopes | `SpendCategoryCreate` | `SpendCategoryRead` | 201【F:app/routers/spend.py†L25-L27】 |
| POST | /spend/merchants | `spend.create_merchant` | API key | Tous scopes | `MerchantCreate` | `MerchantRead` | 201【F:app/routers/spend.py†L30-L32】 |
| POST | /spend/allow | `spend.allow_usage` | API key | Tous scopes | `AllowedUsageCreate` | Statut dict | 201/200【F:app/routers/spend.py†L35-L37】 |
| POST | /spend/purchases | `spend.create_purchase` | API key | Tous scopes | `PurchaseCreate` + `Idempotency-Key` | `PurchaseRead` | 201/403/409【F:app/routers/spend.py†L40-L46】【F:app/services/spend.py†L187-L313】 |
| POST | /spend/allowed | `spend.add_allowed_payee` | API key | Tous scopes | `AddPayeeIn` | Payee dict | 201/409【F:app/routers/spend.py†L49-L74】 |
| POST | /spend | `spend.spend` | API key | Tous scopes | `SpendIn` + `Idempotency-Key` | Paiement dict | 200/409【F:app/routers/spend.py†L77-L105】【F:app/services/usage.py†L80-L236】 |
| POST | /proofs | `proofs.submit_proof` | API key | Tous scopes | `ProofCreate` | `ProofRead` | 201/422【F:app/routers/proofs.py†L11-L18】 |
| POST | /proofs/{id}/decision | `proofs.decide_proof` | API key | Tous scopes | `ProofDecision` | `ProofRead` | 200/400【F:app/routers/proofs.py†L21-L33】 |
| POST | /payments/execute/{id} | `payments.execute_payment` | API key | Tous scopes | Path ID | `PaymentRead` | 200/404/409【F:app/routers/payments.py†L10-L17】 |
| POST | /psp/webhook | `psp.psp_webhook` | Secret PSP | n/a | JSON + headers | Ack dict | 200/401/503【F:app/routers/psp.py†L20-L61】 |

## D. Data model & states
| Entity | Key fields | Constraints / Indexes | Notes |
| --- | --- | --- | --- |
| ApiKey | `name`, `prefix`, `key_hash`, `scope`, `is_active` | Unicité `key_hash` + `prefix` | Base multi-clés avec scopes et dates d’expiration.【F:app/models/api_key.py†L12-L31】 |
| User | `username`, `email`, `is_active` | Unicité username/email | Entité pivot des transactions et mandats.【F:app/models/user.py†L1-L25】 |
| Alert | `type`, `message`, `payload_json` | Index type/date | Journal opérationnel depuis les services.【F:app/models/alert.py†L1-L20】 |
| CertifiedAccount | `user_id`, `level` | Enum + unique `user_id` | Support KYC/merchant.【F:app/models/certified.py†L1-L25】 |
| EscrowAgreement | Parties, `amount_total`, `status`, `deadline_at` | Checks + index statut/date | Source des dépôts/paiements séquestrés.【F:app/models/escrow.py†L1-L40】 |
| EscrowDeposit | `escrow_id`, `amount`, `idempotency_key` | Check >0, unique clé | Empêche double dépôt.【F:app/models/escrow.py†L42-L58】 |
| EscrowEvent | `escrow_id`, `kind`, `data_json` | Index idempotency | Timeline audit.【F:app/models/escrow.py†L60-L69】 |
| Milestone | `escrow_id`, `idx`, `amount`, `proof_type` | Unicités + geofence ≥0 | Support validations EXIF/GPS.【F:app/models/milestone.py†L1-L37】 |
| Proof | `escrow_id`, `milestone_id`, `sha256`, `status` | Hash unique | Pièces justificatives horodatées.【F:app/models/proof.py†L1-L24】 |
| Payment | `escrow_id`, `amount`, `psp_ref`, `status` | Checks + index statut/idempotence | Suivi settlement via webhooks.【F:app/models/payment.py†L1-L33】 |
| Transaction | `sender_id`, `receiver_id`, `amount`, `idempotency_key` | Montants positifs + clé unique | Virements restreints.【F:app/models/transaction.py†L1-L37】 |
| AllowedRecipient | `owner_id`, `recipient_id` | Unique paire | Base allowlist transferts.【F:app/models/allowlist.py†L1-L13】 |
| SpendCategory | `code`, `label` | Code unique | Classification dépenses.【F:app/models/spend.py†L8-L21】 |
| Merchant | `name`, `category_id`, `is_certified` | Nom unique + index | Marchands autorisés/conditionnels.【F:app/models/spend.py†L24-L40】 |
| AllowedUsage | `owner_id`, `merchant_id/category_id` | Contrainte XOR + unicités | Règles d’usage additionnelles.【F:app/models/spend.py†L42-L53】 |
| Purchase | `sender_id`, `merchant_id`, `amount`, `idempotency_key` | Checks + index statut | Achats en Decimal 18,2 audités.【F:app/models/spend.py†L64-L83】 |
| AllowedPayee | `escrow_id`, `payee_ref`, limites | Unique `(escrow_id,payee_ref)` + checks | Payees usage conditionnel.【F:app/models/allowed_payee.py†L1-L26】 |
| UsageMandate | `sender_id`, `beneficiary_id`, `total_amount`, `status`, `total_spent` | Check ≥0 + index actif + unique partiel | Mandats verrouillés par index `status='ACTIVE'`.【F:app/models/usage_mandate.py†L22-L66】【F:alembic/versions/7a4c_unique_active_mandate.py†L1-L19】 |
| PSPWebhookEvent | `event_id`, `psp_ref`, `kind` | Unique event + index | Idempotence des webhooks.【F:app/models/psp_webhook.py†L1-L21】 |
| AuditLog | `actor`, `action`, `entity`, `entity_id` | Dates timezone | Piste commune usages, mandats, paiements.【F:app/models/audit.py†L1-L18】 |

**State machines**
- `EscrowStatus` : DRAFT → FUNDED → RELEASABLE → RELEASED/REFUNDED/CANCELLED avec audit à chaque transition.【F:app/models/escrow.py†L8-L37】【F:app/services/escrow.py†L60-L250】
- `UsageMandateStatus` : ACTIVE → CONSUMED/EXPIRED via consommation atomique ou cron.【F:app/models/usage_mandate.py†L22-L66】【F:app/services/spend.py†L287-L355】【F:app/services/cron.py†L12-L33】
- `PaymentStatus` : PENDING → SENT → SETTLED/ERROR suivant exécution/idempotence/webhook.【F:app/models/payment.py†L1-L31】【F:app/services/psp_webhooks.py†L73-L144】
- `MilestoneStatus` : WAITING → PENDING_REVIEW → APPROVED/REJECTED → PAYING/PAID selon preuves & paiements.【F:app/models/milestone.py†L11-L31】【F:app/services/proofs.py†L139-L214】

## E. Stability results
- `alembic upgrade head` : succès sur SQLite avec 7 révisions séquentielles.【39bb0a†L1-L8】
- `alembic current` : tête unique `7a4c_unique_active_mandate` confirmée.【d52c0a†L1-L4】
- `alembic heads` : aucune branche parallèle détectée.【74d9f1†L1-L2】
- `pytest -q` : 31 tests passés (mandats, usage spend, escrows, webhooks).【33c257†L1-L2】
- Revue statique : handlers FastAPI synchrones, sessions injectées via dépendance `get_db`, logging JSON partagé.【F:app/db.py†L1-L109】【F:app/core/logging.py†L1-L27】
- Idempotence/transactions : helpers communs utilisés pour dépôts, paiements, achats et webhooks.【F:app/services/idempotency.py†L10-L41】【F:app/services/escrow.py†L101-L165】【F:app/services/spend.py†L287-L339】【F:app/services/psp_webhooks.py†L54-L114】

## F. Security & integrity
- AuthN/AuthZ : `require_api_key` valide Bearer et legacy ; scopes disponibles mais non consommés côté routes métier.【F:app/security.py†L13-L47】【F:app/routers/users.py†L11-L31】
- API keys : hash HMAC côté serveur, champ `is_active`/`expires_at` mais absence de mise à jour `last_used_at` ou audit à la création.【F:app/models/api_key.py†L18-L31】【F:app/routers/apikeys.py†L24-L49】
- Mandats : validation d’existences, anti-doublon, audit sur création/expiration et décrément atomique pour éviter les courses.【F:app/services/mandates.py†L68-L176】【F:app/services/spend.py†L287-L355】
- PSP : secret imposé au démarrage, signature HMAC + timestamp, idempotence par `event_id` + audit Payment.【F:app/main.py†L23-L45】【F:app/routers/psp.py†L20-L61】【F:app/services/psp_webhooks.py†L20-L144】
- Preuves : validations EXIF/GPS, classification des erreurs, auto-approbation des milestones et audit systématique.【F:app/services/proofs.py†L45-L214】
- Audit & logs : `AuditLog` alimenté pour mandats, achats, escrows, paiements et usage payee ; logs JSON uniformes.【F:app/models/audit.py†L1-L18】【F:app/services/spend.py†L342-L369】【F:app/services/escrow.py†L74-L250】【F:app/services/usage.py†L46-L233】

## G. Observability & ops
- Lifespan unique : init/dispose moteur SQL, scheduler démarré/arrêté proprement.【F:app/main.py†L23-L45】【F:app/db.py†L1-L109】
- CORS : origines restreintes via settings (kobatela + localhost).【F:app/config.py†L19-L25】【F:app/main.py†L52-L58】
- Cron maintenance : APScheduler en mémoire, tâche horaire `expire_mandates_once` (pas de job store partagé).【F:app/main.py†L33-L40】【F:app/services/cron.py†L12-L33】
- Metrics & Sentry : Prometheus exporter activable (`PROMETHEUS_ENABLED`), Sentry initialisé si DSN présent.【F:app/config.py†L19-L25】【F:app/main.py†L60-L69】
- Build/tests : pipeline local basé sur Alembic + pytest, pas de lint intégré dans `requirements.txt`.

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Auth | `DEV_API_KEY` par défaut ouvre tous les endpoints si fuite (aucune rotation) | Critique | Moyen | **P0** | Désactiver la clé legacy en staging/prod, imposer des clés explicites par env.【F:app/config.py†L11-L25】【F:app/utils/apikey.py†L31-L45】 |
| R2 | AuthZ | Scopes inutilisés : toute clé active accède à l’ensemble des routes | Élevé | Élevé | **P1** | Mapper les scopes (`sender/support/admin`) aux routeurs critiques via `require_scope` et tests dédiés.【F:app/security.py†L35-L47】【F:app/routers/users.py†L11-L31】 |
| R3 | Audit sécurité | Création/utilisation des clés API sans audit ni mise à jour `last_used_at` | Moyen | Moyen | **P1** | Ajouter audit `AuditLog` et mise à jour `last_used_at` lors de la validation dans `find_valid_key`.【F:app/models/api_key.py†L18-L31】【F:app/utils/apikey.py†L31-L45】 |
| R4 | Ops | Cron APScheduler local à chaque process → double exécution ou arrêt si pod down | Moyen | Moyen | **P2** | Externaliser vers worker dédié ou job store partagé, ou migrer vers tâche DB transactionnelle. 【F:app/main.py†L33-L45】【F:app/services/cron.py†L12-L33】 |
| R5 | Gouvernance clés | Pas d’endpoint de révocation/désactivation malgré `is_active` | Moyen | Moyen | **P2** | Exposer endpoints admin pour lister/révoquer et couvrir par tests RBAC. 【F:app/models/api_key.py†L18-L31】【F:app/routers/apikeys.py†L18-L49】 |

## I. Roadmap to MVP-ready
- **P0** : Neutraliser `DEV_API_KEY` en environnements partagés et fournir clés distinctes par équipe.【F:app/config.py†L11-L25】
- **P1** :
  - Appliquer `require_scope` sur les routeurs (ex. spend, mandates, escrows) et ajouter tests d’accès par scope.【F:app/security.py†L35-L47】【F:app/routers/spend.py†L17-L105】
  - Étendre `find_valid_key` pour tracer `last_used_at` + audit `AuditLog` lors de la création/révocation des clés.【F:app/utils/apikey.py†L31-L45】【F:app/routers/apikeys.py†L24-L49】
- **P2** :
  - Externaliser ou fiabiliser le cron d’expiration (job worker ou DB), exposer endpoints de gestion des clés (`GET/DELETE /apikeys/{id}`) et documenter `/metrics`.【F:app/services/cron.py†L12-L33】【F:app/routers/apikeys.py†L18-L49】

**Verdict : NO-GO** — ouvrir uniquement après suppression de la clé legacy et enforcement des scopes API.
