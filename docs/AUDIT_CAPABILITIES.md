# Kobatela_alpha — Capability & Stability Audit (2025-11-11)

## A. Executive summary
- ✅ Couche monétaire homogène : montants d'achats et mandats sont stockés en `Decimal` via modèles et migration dédiés, éliminant les dérives binaires.【F:app/models/spend.py†L64-L83】【F:app/models/usage_mandate.py†L22-L45】【F:alembic/versions/2c2680073b35_use_decimal_for_purchases_amount.py†L17-L38】
- ✅ Contrôles mandataires dynamiques : chaque achat vérifie marchand, catégorie, expiration et solde avant validation, avec tests HTTP couvrant les refus attendus.【F:app/services/spend.py†L133-L212】【F:tests/test_usage_mandates.py†L43-L169】
- ✅ Webhook PSP durci : secret obligatoire, HMAC+timestamp, idempotence évènementielle et journalisation des règlements.【F:app/routers/psp.py†L20-L61】【F:app/services/psp_webhooks.py†L20-L144】【F:tests/test_psp_webhook.py†L32-L134】
- ✅ Escrow traçable : chaque transition (création, dépôt, preuve, approbation) émet un `AuditLog`, garantissant la piste comptable.【F:app/services/escrow.py†L40-L119】【F:tests/test_escrow.py†L75-L120】
- ✅ Suite de tests représentative : 29 tests couvrent mandats, dépenses, webhooks et escrows, assurant une régression rapide.【F:tests/test_usage_mandates.py†L1-L194】【F:tests/test_spend.py†L11-L200】【F:tests/test_psp_webhook.py†L32-L134】【1eef49†L1-L3】
- ⚠️ P0 — Mandats non scellés au financeur : la recherche de mandat n'inclut pas `sender_id`, permettant de détourner le budget d'un autre expéditeur.【F:app/services/spend.py†L135-L143】
- ⚠️ P0 — Concurrence sur la balance : décrément du mandat sans verrou ni requête atomique → deux achats simultanés peuvent dépasser le plafond.【F:app/services/spend.py†L254-L268】
- ⚠️ P1 — Clé API unique et par défaut : une seule clé statique `dev-secret-key` suffit pour accéder à tout le backend.【F:app/config.py†L11-L38】【F:app/security.py†L7-L21】
- ⚠️ P1 — Mandats sans audit trail : création et expiration ne produisent aucun `AuditLog`, compliquant les investigations.【F:app/services/mandates.py†L45-L102】
- ⚠️ P2 — Expiration manuelle : le nettoyage des mandats repose sur une invocation `/mandates/cleanup` non planifiée.【F:app/routers/mandates.py†L12-L27】
- Readiness score: **45 / 100** — les P0 sur l'authentification du mandat et la concurrence empêchent tout pilote externe.

## B. Capability map (current, concrete)
### B.1 Feature coverage
| Feature | Implemented endpoints/modules | Status | Notes |
| --- | --- | --- | --- |
| Santé & métadonnées | `GET /health` → `health.healthcheck` | Implémenté | Ping simple sans dépendances.【F:app/routers/health.py†L4-L11】 |
| Création utilisateurs | `POST /users`, `GET /users/{id}` | Implémenté | CRUD basique protégé par clé API.【F:app/routers/users.py†L12-L31】 |
| Alertes opérationnelles | `GET /alerts` | Implémenté | Filtre par type avec dépendance DB synchrone.【F:app/routers/alerts.py†L11-L19】 |
| Escrow lifecycle | `/escrows` + service | Implémenté | Gestion complète avec idempotence dépôts et audits.【F:app/routers/escrow.py†L12-L63】【F:app/services/escrow.py†L40-L149】 |
| Allowlist & certification | `/allowlist`, `/certified` | Implémenté | Contrôles de doublons et estampille temps.【F:app/routers/transactions.py†L27-L64】 |
| Transactions restreintes | `POST /transactions` | Implémenté | Idempotence via header et service dédié.【F:app/routers/transactions.py†L66-L75】【F:app/services/transactions.py†L25-L86】 |
| Mandats d'usage | `/mandates`, `/mandates/cleanup` | Partiel | Création et expiration OK mais failles P0 sur rattachement et concurrence.【F:app/routers/mandates.py†L12-L27】【F:app/services/spend.py†L135-L268】 |
| Spend categories & merchants | `/spend/categories`, `/spend/merchants` | Implémenté | Gestion CRUD + contrôles d'unicité.【F:app/routers/spend.py†L25-L33】【F:app/services/spend.py†L24-L88】 |
| Purchases conditionnels | `POST /spend/purchases` | Partiel | Vérifie mandat/allowlist mais vulnérable aux P0 identifiés.【F:app/routers/spend.py†L40-L46】【F:app/services/spend.py†L133-L286】 |
| Usage payees & payouts | `/spend/allowed`, `/spend` | Implémenté | Limites quotidiennes/totales + idempotence paiement.【F:app/routers/spend.py†L57-L105】【F:app/services/usage.py†L23-L198】 |
| Proofs & géofence | `/proofs`, `/proofs/{id}/decision` | Implémenté | Contrôles EXIF, géofence et audit.【F:app/routers/proofs.py†L11-L33】【F:app/services/proofs.py†L45-L198】 |
| Paiements sortants & webhooks | `/payments/execute/{id}`, `/psp/webhook` | Partiel | Exécution interne OK, dépend du renforcement clé API côté PSP.【F:app/routers/payments.py†L10-L17】【F:app/routers/psp.py†L20-L61】 |

### B.2 Supported end-to-end flows (today)
- Mandat conditionnel diaspora → bénéficiaire : création utilisateurs → `/mandates` → `/spend/purchases` avec contrôles marchand/catégorie et décrément du mandat.【F:app/routers/users.py†L12-L31】【F:app/routers/mandates.py†L12-L27】【F:app/services/spend.py†L133-L286】
- Escrow basé sur preuves : `/escrows` → dépôt idempotent → `/proofs` → approbation client avec audit complet.【F:app/routers/escrow.py†L12-L63】【F:app/services/escrow.py†L40-L149】【F:app/services/proofs.py†L45-L198】
- Transaction restreinte : `/allowlist` → `/transactions` (clé d'idempotence) → lecture transaction.【F:app/routers/transactions.py†L27-L87】【F:app/services/transactions.py†L25-L86】
- Payout PSP : `/payments/execute/{id}` → webhook PSP signé qui clôture le paiement et journalise.【F:app/routers/payments.py†L10-L17】【F:app/services/psp_webhooks.py†L20-L144】

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request | Response | Codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | /health | `health.healthcheck` | Aucun | n/a | – | `{status:str}` | 200【F:app/routers/health.py†L4-L11】 |
| POST | /users | `users.create_user` | API key | n/a | `UserCreate` | `UserRead` | 201【F:app/routers/users.py†L12-L23】 |
| GET | /users/{id} | `users.get_user` | API key | n/a | Path ID | `UserRead` | 200/404【F:app/routers/users.py†L25-L31】 |
| GET | /alerts | `alerts.list_alerts` | API key | n/a | Query `type` | `list[AlertRead]` | 200【F:app/routers/alerts.py†L11-L19】 |
| POST | /escrows | `escrow.create_escrow` | API key | n/a | `EscrowCreate` | `EscrowRead` | 201【F:app/routers/escrow.py†L12-L17】 |
| POST | /escrows/{id}/deposit | `escrow.deposit` | API key | n/a | `EscrowDepositCreate` + `Idempotency-Key` | `EscrowRead` | 200/409【F:app/routers/escrow.py†L20-L27】 |
| POST | /escrows/{id}/mark-delivered | `escrow.mark_delivered` | API key | n/a | `EscrowActionPayload` | `EscrowRead` | 200【F:app/routers/escrow.py†L30-L33】 |
| POST | /escrows/{id}/client-approve | `escrow.client_approve` | API key | n/a | Body optionnel | `EscrowRead` | 200【F:app/routers/escrow.py†L35-L41】 |
| POST | /escrows/{id}/client-reject | `escrow.client_reject` | API key | n/a | Body optionnel | `EscrowRead` | 200【F:app/routers/escrow.py†L44-L50】 |
| POST | /escrows/{id}/check-deadline | `escrow.check_deadline` | API key | n/a | Path ID | `EscrowRead` | 200【F:app/routers/escrow.py†L53-L55】 |
| GET | /escrows/{id} | `escrow.read_escrow` | API key | n/a | Path ID | `EscrowRead` | 200/404【F:app/routers/escrow.py†L58-L63】 |
| POST | /allowlist | `transactions.add_to_allowlist` | API key | n/a | `AllowlistCreate` | Statut dict | 201/200【F:app/routers/transactions.py†L27-L44】 |
| POST | /certified | `transactions.add_certification` | API key | n/a | `CertificationCreate` | Statut dict | 201/200【F:app/routers/transactions.py†L46-L64】 |
| POST | /transactions | `transactions.post_transaction` | API key | n/a | `TransactionCreate` + `Idempotency-Key` | `TransactionRead` | 201/409【F:app/routers/transactions.py†L66-L75】 |
| GET | /transactions/{id} | `transactions.get_transaction` | API key | n/a | Path ID | `TransactionRead` | 200/404【F:app/routers/transactions.py†L78-L88】 |
| POST | /mandates | `mandates.create_mandate` | API key | n/a | `UsageMandateCreate` | `UsageMandateRead` | 201【F:app/routers/mandates.py†L12-L19】 |
| POST | /mandates/cleanup | `mandates.cleanup_expired_mandates` | API key | n/a | – | `{expired:int}` | 202【F:app/routers/mandates.py†L22-L27】 |
| POST | /spend/categories | `spend.create_category` | API key | n/a | `SpendCategoryCreate` | `SpendCategoryRead` | 201【F:app/routers/spend.py†L25-L27】 |
| POST | /spend/merchants | `spend.create_merchant` | API key | n/a | `MerchantCreate` | `MerchantRead` | 201【F:app/routers/spend.py†L30-L32】 |
| POST | /spend/allow | `spend.allow_usage` | API key | n/a | `AllowedUsageCreate` | Statut dict | 201/200【F:app/routers/spend.py†L35-L37】 |
| POST | /spend/purchases | `spend.create_purchase` | API key | n/a | `PurchaseCreate` + `Idempotency-Key` | `PurchaseRead` | 201/403【F:app/routers/spend.py†L40-L46】 |
| POST | /spend/allowed | `spend.add_allowed_payee` | API key | n/a | `AddPayeeIn` | Payee dict | 201/409【F:app/routers/spend.py†L49-L74】 |
| POST | /spend | `spend.spend` | API key | n/a | `SpendIn` + `Idempotency-Key` | Paiement dict | 200/409【F:app/routers/spend.py†L77-L105】 |
| POST | /proofs | `proofs.submit_proof` | API key | n/a | `ProofCreate` | `ProofRead` | 201/422【F:app/routers/proofs.py†L11-L18】 |
| POST | /proofs/{id}/decision | `proofs.decide_proof` | API key | n/a | `ProofDecision` | `ProofRead` | 200/400【F:app/routers/proofs.py†L21-L33】 |
| POST | /payments/execute/{id} | `payments.execute_payment` | API key | n/a | Path ID | `PaymentRead` | 200/404/409【F:app/routers/payments.py†L10-L17】 |
| POST | /psp/webhook | `psp.psp_webhook` | Aucun | n/a | JSON + headers PSP | Ack dict | 200/401/503【F:app/routers/psp.py†L20-L61】 |

## D. Data model & states
| Entity | Key fields | Constraints / Indexes | Notes |
| --- | --- | --- | --- |
| User | `username`, `email`, `is_active` | Unicité username/email | Base identity pour toutes les relations.【F:app/models/user.py†L1-L35】 |
| Alert | `type`, `message`, `actor_user_id` | Index par type/date | Flux d'alertes opérationnelles.【F:app/models/alert.py†L1-L26】 |
| CertifiedAccount | `user_id`, `level` | Enum + unicité `user_id` | Certification marchands/utilisateurs.【F:app/models/certified.py†L1-L28】 |
| EscrowAgreement | Parties, `amount_total`, `status`, `deadline_at` | Check >=0, index statut/deadline | Pilote preuves et paiements.【F:app/models/escrow.py†L1-L68】 |
| EscrowDeposit | `escrow_id`, `amount`, `idempotency_key` | Check >0, unique idempotency | Garantit dépôts idempotents.【F:app/models/escrow.py†L40-L58】 |
| EscrowEvent | `escrow_id`, `kind`, `data_json` | Index multiples | Chronologie des actions escrow.【F:app/models/escrow.py†L58-L69】 |
| Milestone | `escrow_id`, `idx`, `amount`, géofence | Unicités + champs géo | Support validations GPS.【F:app/models/milestone.py†L1-L47】 |
| Proof | `escrow_id`, `milestone_id`, `sha256`, `status` | Unicité hash | Stockage des preuves avec EXIF.【F:app/models/proof.py†L1-L24】 |
| Payment | `escrow_id`, `amount`, `psp_ref`, `status` | Check >0, unicité ref | Suivi PSP + idempotence.【F:app/models/payment.py†L1-L38】 |
| Transaction | `sender_id`, `receiver_id`, `amount`, `idempotency_key` | Check >0, unique key | Transferts restreints.【F:app/models/transaction.py†L1-L37】 |
| AllowedRecipient | `owner_id`, `recipient_id` | Unicité paire | Allowlist anti-fraude.【F:app/models/allowlist.py†L1-L15】 |
| AllowedPayee | `escrow_id`, `payee_ref`, limites | Unicité `(escrow_id, payee_ref)` | Limites quotidiennes/totales.【F:app/models/allowed_payee.py†L1-L32】 |
| SpendCategory | `code`, `label` | Code unique | Classification mandat usage.【F:app/models/spend.py†L1-L21】 |
| Merchant | `name`, `category_id`, `is_certified` | Nom unique, index catégorie | Acteurs commerciaux certifiés ou non.【F:app/models/spend.py†L24-L53】 |
| AllowedUsage | `owner_id`, `merchant_id/category_id` | Check exclusif + unicités | Règles d'autorisation hors mandat.【F:app/models/spend.py†L37-L53】 |
| Purchase | `sender_id`, `merchant_id`, `amount`, `idempotency_key` | Check >0, index statut | Dépenses conditionnelles en Decimal.【F:app/models/spend.py†L64-L83】 |
| UsageMandate | `sender_id`, `beneficiary_id`, `total_amount`, `status` | Check >=0, index multiples | Mandat diaspora ↔ bénéficiaire.【F:app/models/usage_mandate.py†L22-L45】 |
| PSPWebhookEvent | `event_id`, `psp_ref`, `kind` | Unicité event | Idempotence webhook.【F:app/models/psp_webhook.py†L1-L21】 |
| AuditLog | `actor`, `action`, `entity`, `entity_id` | Timestamps auto | Piste d'audit centrale.【F:app/models/audit.py†L1-L20】 |

**State machines**
- `EscrowStatus` : DRAFT → FUNDED → RELEASABLE → RELEASED/REFUNDED/CANCELLED, orchestré par le service avec audits systématiques.【F:app/models/escrow.py†L12-L20】【F:app/services/escrow.py†L83-L149】
- `UsageMandateStatus` : ACTIVE → CONSUMED/EXPIRED via achats ou nettoyage programmé.【F:app/models/usage_mandate.py†L14-L45】【F:app/services/spend.py†L254-L258】【F:app/services/mandates.py†L84-L102】
- `PurchaseStatus` : COMPLETED par défaut, autres statuts réservés pour extensions futures.【F:app/models/spend.py†L56-L83】
- `PaymentStatus` : PENDING → SENT → SETTLED/ERROR suivant les webhooks PSP.【F:app/models/payment.py†L1-L38】【F:app/services/psp_webhooks.py†L85-L144】
- `MilestoneStatus` : WAITING → PENDING_REVIEW → APPROVED/REJECTED → PAYING/PAID selon preuves et paiements.【F:app/models/milestone.py†L11-L31】【F:app/services/proofs.py†L139-L185】

## E. Stability results
- `pytest -q` : 29 tests passés, 0 échec, 1.59 s.【1eef49†L1-L3】
- `alembic upgrade head` rejoue les trois révisions (init, Decimal, mandats) sans erreur.【63d715†L1-L5】
- `alembic current` confirme la tête unique `5b91fcb4d6af`; `alembic heads` ne montre aucune branche parallèle.【c68ae8†L1-L4】【2e0b1c†L1-L2】
- Pas d'outils lint référencés ; revue manuelle : dépendances synchrone/SQLAlchemy, pas d'`async` bloquant identifié.
- Idempotence : helpers partagés empêchent les doubles débits pour achats, dépôts escrow et paiements conditionnels.【F:app/services/idempotency.py†L10-L41】【F:app/services/spend.py†L120-L269】【F:app/services/escrow.py†L62-L116】【F:app/services/usage.py†L91-L198】

## F. Security & integrity
- AuthN/AuthZ : sécurité basée sur une seule clé API Bearer, sans scopes ni rotation, exposant toute la surface en cas de fuite.【F:app/security.py†L7-L21】【F:app/config.py†L11-L38】
- Mandats : validation utilisateur/marchand/catégorie, contrôle d'expiration et solde mais absence de filtrage par expéditeur et d'audit trail.【F:app/services/mandates.py†L45-L102】【F:app/services/spend.py†L135-L268】
- PSP : secret requis au démarrage, signature HMAC + skew temporel, idempotence des événements et audit des paiements.【F:app/main.py†L17-L38】【F:app/routers/psp.py†L20-L61】【F:app/services/psp_webhooks.py†L20-L144】
- Validation entrées : schémas Pydantic contraignent montants positifs, devises et structures des charges.【F:app/schemas/spend.py†L1-L86】【F:app/schemas/transaction.py†L1-L44】【F:app/schemas/escrow.py†L1-L57】
- Preuves : pipeline EXIF/GPS, normalisation d'erreurs et haversine pour géofence.【F:app/services/proofs.py†L45-L198】
- Audit & logs : logging JSON centralisé et audit sur escrows/paiements/dépenses, manque pour mandats.【F:app/core/logging.py†L10-L31】【F:app/services/escrow.py†L40-L149】【F:app/services/psp_webhooks.py†L85-L144】【F:app/services/spend.py†L273-L285】【F:app/services/mandates.py†L45-L102】

## G. Observability & ops
- Initialisation via lifespan : logging configuré, vérification du secret PSP, création/fermeture moteur DB garanties.【F:app/main.py†L17-L61】【F:app/db.py†L1-L109】
- CORS permissif (`*`) adapté au prototypage mais à restreindre pour la prod.【F:app/main.py†L31-L40】
- Migrations alignées : trois révisions cohérentes (init, Decimal, mandats) avec index appropriés.【F:alembic/versions/baa4932d9a29_0001_init_schema.py†L1-L199】【F:alembic/versions/2c2680073b35_use_decimal_for_purchases_amount.py†L17-L58】【F:alembic/versions/5b91fcb4d6af_add_usage_mandates_table.py†L18-L87】
- Gestion SQLite : PRAGMA foreign keys et sessionmaker paresseux pour tests locaux.【F:app/db.py†L18-L109】
- Aucune tâche planifiée : nettoyage de mandats dépend d'un appel manuel, aucun worker intégré.【F:app/routers/mandates.py†L22-L27】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Spend mandates | Mandat appliqué sans vérifier `sender_id` → un bénéficiaire peut dépenser le budget d'un autre financeur. | Très élevé (fraude directe) | Probable (surface triviale) | P0 | Ajouter filtre `UsageMandate.sender_id == payload.original_sender_id` + tests négatifs.【F:app/services/spend.py†L135-L143】 |
| R2 | Spend mandates | Décrément du solde en mémoire sans verrou ; deux achats parallèles peuvent dépasser `total_amount`. | Très élevé (dépassement plafond) | Probable (multi-clients) | P0 | Utiliser `SELECT ... FOR UPDATE`/`with_for_update` ou `UPDATE ... WHERE total_amount >= amount` atomique, sinon transaction sérialisée.【F:app/services/spend.py†L254-L268】 |
| R3 | Mandate service | Aucun `AuditLog` pour création/expiration de mandat. | Élevé (traçabilité manquante) | Elevé | P1 | Insérer un audit `USAGE_MANDATE_CREATED/EXPIRED/CONSUMED` dans le service.【F:app/services/mandates.py†L45-L102】 |
| R4 | API security | Clé API unique `dev-secret-key` en clair. | Élevé (compromission totale) | Elevé | P1 | Externaliser dans secret manager, permettre clés multiples/rotation + scopes par rôle.【F:app/config.py†L11-L38】【F:app/security.py†L7-L21】 |
| R5 | Mandate ops | Expiration dépend d'un endpoint manuel `/mandates/cleanup`. | Moyen (mandats périmés actifs) | Moyen | P2 | Planifier cron/worker ou vérifier expiration côté achat + jobs récurrents.【F:app/routers/mandates.py†L22-L27】 |

## I. Roadmap to MVP-ready
- **P0** :
  - Filtrer les mandats par `sender_id` + verrou transactionnel/UPDATE atomique pour la décrémentation.【F:app/services/spend.py†L135-L268】
- **P1** :
  - Ajouter audit trail (create/consume/expire) sur les mandats et renforcer la gouvernance des clés API (rotation, scopes).【F:app/services/mandates.py†L45-L102】【F:app/security.py†L7-L21】
- **P2** :
  - Automatiser la révocation des mandats expirés (cron, worker) et restreindre CORS en production.【F:app/routers/mandates.py†L22-L27】【F:app/main.py†L31-L40】

**Verdict : NO-GO tant que les correctifs P0 ne sont pas livrés et vérifiés en tests de charge concurrente.**
