# Kobatela_alpha — Capability & Stability Audit (2025-11-10)

## A. Executive summary
- ✅ Couche monétaire homogène : montants d'achats et mandats sont en `Decimal` avec migrations dédiées, ce qui évite les arrondis binaires et facilite les contrôles d'intégrité.【F:app/models/spend.py†L64-L83】【F:app/models/usage_mandate.py†L22-L45】【F:alembic/versions/2c2680073b35_use_decimal_for_purchases_amount.py†L17-L58】
- ✅ Mandats d'usage actifs : le service d'orchestration vérifie la catégorie, le marchand, la devise et la balance restante avant toute dépense, avec tests API couvrant les refus attendus.【F:app/services/spend.py†L117-L286】【F:tests/test_usage_mandates.py†L1-L164】
- ✅ Webhook PSP durci : la route impose un secret configuré, vérifie HMAC + dérive temporelle et refuse toute configuration absente, limitant les fraudes de règlement.【F:app/routers/psp.py†L1-L54】【F:app/services/psp_webhooks.py†L1-L96】
- ✅ Traçabilité financière : les escrows et paiements émettent des `AuditLog` structurés à chaque transition critique, consolidant la piste d'audit comptable.【F:app/services/escrow.py†L1-L213】【F:app/services/psp_webhooks.py†L60-L96】
- ✅ Outillage fiable : 29 tests asynchrones couvrent mandats, dépenses, webhooks et escrows, exécutés avec succès, gage de régression rapide.【855b8e†L1-L2】【F:tests/test_usage_mandates.py†L1-L194】
- ⚠️ P0 — Mandat non scellé au donneur : `create_purchase` ne filtre que par bénéficiaire et devise, permettant qu'un mandat financé par un expéditeur soit détourné par un autre, ce qui casse l'engagement contractuel.【F:app/services/spend.py†L135-L143】
- ⚠️ P0 — Concurrence sur la balance : deux achats simultanés recalculent la même balance et écrasent la valeur sans verrou, autorisant une dépense cumulée supérieure au plafond du mandat.【F:app/services/spend.py†L254-L258】
- ⚠️ P1 — Authentification globale : l'ensemble des routes (hors /health) reposent sur une API key unique non scindée par rôle ni rotation, insuffisant pour un produit financier.【F:app/security.py†L1-L21】【F:app/routers/__init__.py†L10-L20】
- ⚠️ P1 — Mandats sans historique : aucune entrée d'audit n'est créée lors de la création ou de la consommation d'un mandat, compliquant les investigations sur l'usage conditionnel.【F:app/services/mandates.py†L45-L102】
- ⚠️ P2 — Nettoyage manuel : l'expiration des mandats repose sur un endpoint `/mandates/cleanup` appelé manuellement, sans planification ni garde automatique côté achat, ce qui peut laisser des mandats périmés actifs si la tâche n'est pas lancée.【F:app/routers/mandates.py†L12-L27】【F:app/services/mandates.py†L84-L102】
- Readiness score: **50 / 100** — les fonctionnalités principales existent, mais les deux P0 sur la vérification des mandats bloquent un pilote externe.

## B. Capability map (current, concrete)
### B.1 Feature coverage
| Feature | Implemented endpoints/modules | Status | Notes |
| --- | --- | --- | --- |
| Santé & métadonnées | `GET /health` → `health.healthcheck` | Implémenté | Ping simple sans dépendance.【F:app/routers/health.py†L1-L11】 |
| Création utilisateurs | `POST /users`, `GET /users/{id}` | Implémenté | CRUD basique protégé par API key.【F:app/routers/users.py†L1-L31】 |
| Alertes | `GET /alerts` | Implémenté | Liste filtrable pour signaux opérationnels.【F:app/routers/alerts.py†L1-L19】 |
| Escrow lifecycle | Routes escrow + service | Implémenté | Création, dépôts, livraisons et décisions avec audit trail ajouté.【F:app/routers/escrow.py†L1-L63】【F:app/services/escrow.py†L1-L213】 |
| Allowlist & certification | `/allowlist`, `/certified` | Implémenté | Ajout d'allowlist et niveaux de certification avec validations.【F:app/routers/transactions.py†L27-L63】 |
| Transactions restreintes | `POST /transactions` | Implémenté | Vérifie allowlist + idempotence, journalise les décisions.【F:app/routers/transactions.py†L66-L87】【F:app/services/transactions.py†L25-L86】 |
| Mandats d'usage | `/mandates`, `/mandates/cleanup` | Partiel | Création et expiration de mandats, mais failles P0 sur filtrage et concurrence.【F:app/routers/mandates.py†L12-L27】【F:app/services/mandates.py†L45-L102】 |
| Spend categories & merchants | `/spend/categories`, `/spend/merchants` | Implémenté | Permet de structurer les politiques de dépense.【F:app/routers/spend.py†L25-L33】 |
| Purchases conditionnels | `POST /spend/purchases` | Partiel | Vérifie mandats/allowlist/certif mais vulnérable aux deux P0 identifiés.【F:app/routers/spend.py†L40-L46】【F:app/services/spend.py†L117-L286】 |
| Usage payees | `/spend/allowed`, `/spend` | Implémenté | Dépenses idempotentes vers payés autorisés avec limites quotidiennes/total.【F:app/routers/spend.py†L57-L105】【F:app/services/usage.py†L23-L235】 |
| Proofs & géofence | `/proofs`, `/proofs/{id}/decision` | Implémenté | Contrôles EXIF/géofence avant déblocage des milestones.【F:app/routers/proofs.py†L1-L33】【F:app/services/proofs.py†L45-L318】 |
| Paiements sortants | `POST /payments/execute/{id}` + webhook PSP | Partiel | Exécution et confirmations gérées, dépend du renforcement PSP et gouvernance clé API.【F:app/routers/payments.py†L1-L17】【F:app/routers/psp.py†L1-L54】 |

### B.2 Supported end-to-end flows (today)
- **Mandat conditionnel diaspora → bénéficiaire** : créer utilisateurs → poster `/mandates` → initier `/spend/purchases` avec contrôles de marchand/catégorie et décrément de balance.【F:app/routers/users.py†L1-L31】【F:app/routers/mandates.py†L12-L27】【F:app/services/spend.py†L117-L286】
- **Escrow basé sur preuves** : `/escrows` → dépôt idempotent → `/proofs` avec validation EXIF → décision client qui déclenche audit + paiement.【F:app/routers/escrow.py†L1-L63】【F:app/services/escrow.py†L1-L213】【F:app/services/proofs.py†L45-L318】
- **Transaction restreinte** : `/allowlist` → `/transactions` avec clé d'idempotence → audit et alerte en cas de refus.【F:app/routers/transactions.py†L27-L87】【F:app/services/transactions.py†L25-L86】
- **Payout PSP** : `/payments/execute/{id}` → webhook PSP signé qui fixe le statut et écrit un audit.【F:app/routers/payments.py†L1-L17】【F:app/services/psp_webhooks.py†L1-L96】

## C. Endpoint inventory
| Method | Path | Handler | Auth | Roles | Request | Response | Codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | /health | `health.healthcheck` | Aucun | n/a | – | Dict statut | 200【F:app/routers/health.py†L1-L11】 |
| POST | /users | `users.create_user` | API key | n/a | `UserCreate` | `UserRead` | 201【F:app/routers/users.py†L1-L22】 |
| GET | /users/{user_id} | `users.get_user` | API key | n/a | Path ID | `UserRead` | 200/404【F:app/routers/users.py†L24-L31】 |
| GET | /alerts | `alerts.list_alerts` | API key | n/a | Query `type` | `list[AlertRead]` | 200【F:app/routers/alerts.py†L1-L19】 |
| POST | /escrows | `escrow.create_escrow` | API key | n/a | `EscrowCreate` | `EscrowRead` | 201【F:app/routers/escrow.py†L1-L17】 |
| POST | /escrows/{id}/deposit | `escrow.deposit` | API key | n/a | `EscrowDepositCreate` + `Idempotency-Key` | `EscrowRead` | 200【F:app/routers/escrow.py†L20-L27】 |
| POST | /escrows/{id}/mark-delivered | `escrow.mark_delivered` | API key | n/a | `EscrowActionPayload` | `EscrowRead` | 200【F:app/routers/escrow.py†L30-L33】 |
| POST | /escrows/{id}/client-approve | `escrow.client_approve` | API key | n/a | Optional payload | `EscrowRead` | 200【F:app/routers/escrow.py†L35-L41】 |
| POST | /escrows/{id}/client-reject | `escrow.client_reject` | API key | n/a | Optional payload | `EscrowRead` | 200【F:app/routers/escrow.py†L44-L50】 |
| POST | /escrows/{id}/check-deadline | `escrow.check_deadline` | API key | n/a | Path ID | `EscrowRead` | 200【F:app/routers/escrow.py†L53-L55】 |
| GET | /escrows/{id} | `escrow.read_escrow` | API key | n/a | Path ID | `EscrowRead` | 200/404【F:app/routers/escrow.py†L58-L63】 |
| POST | /allowlist | `transactions.add_to_allowlist` | API key | n/a | `AllowlistCreate` | Statut dict | 200/201【F:app/routers/transactions.py†L27-L43】 |
| POST | /certified | `transactions.add_certification` | API key | n/a | `CertificationCreate` | Statut dict | 200/201【F:app/routers/transactions.py†L46-L63】 |
| POST | /transactions | `transactions.post_transaction` | API key | n/a | `TransactionCreate` + `Idempotency-Key` | `TransactionRead` | 201【F:app/routers/transactions.py†L66-L75】 |
| GET | /transactions/{id} | `transactions.get_transaction` | API key | n/a | Path ID | `TransactionRead` | 200/404【F:app/routers/transactions.py†L78-L87】 |
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
| R1 | Usage mandates | Mandat sélectionné uniquement par bénéficiaire/devise ; un autre expéditeur peut consommer les fonds. | Critique | Élevée | P0 | Ajouter filtre `sender_id` et éventuellement un index unique `(sender_id, beneficiary_id, status='ACTIVE')` dans la requête/migration.【F:app/services/spend.py†L135-L143】【F:app/models/usage_mandate.py†L22-L45】 |
| R2 | Usage mandates | Absence de verrouillage lors du décrément de balance → deux achats simultanés dépassent le plafond autorisé. | Critique | Moyenne | P0 | Charger le mandat `FOR UPDATE` ou utiliser `UPDATE ... WHERE total_amount >= montant` pour garantir l'atomicité, et rejeter si 0 ligne mise à jour.【F:app/services/spend.py†L254-L258】 |
| R3 | Mandate auditing | Création/expiration/consommation sans `AuditLog`, rendant l'usage non traçable. | Élevé | Moyenne | P1 | Insérer des audits dans `create_mandate`, `close_expired_mandates` et la consommation dans `create_purchase`.【F:app/services/mandates.py†L45-L102】【F:app/services/spend.py†L243-L286】 |
| R4 | Auth global | API key unique, pas de rotation ni scopes. | Élevé | Moyenne | P1 | Introduire JWT/clé par client + rotation + journalisation d'accès.【F:app/security.py†L1-L21】 |
| R5 | Expiration mandats | Endpoint `/mandates/cleanup` à déclenchement manuel ; un oubli laisse des mandats expirés actifs (jusqu'à une tentative d'achat). | Moyen | Moyenne | P2 | Programmer une tâche périodique (cron worker) ou déclencher lors de chaque achat via job asynchrone.【F:app/routers/mandates.py†L22-L27】【F:app/services/mandates.py†L84-L102】 |

## I. Roadmap to MVP-ready
- **P0**
  - Filtrer les mandats par `sender_id` lors des achats et ajouter un verrou atomique sur la mise à jour de balance (migration + requête conditionnelle).【F:app/services/spend.py†L135-L258】
  - Couvrir mandats par AuditLog (création, consommation, expiration) et tests associés.【F:app/services/mandates.py†L45-L102】【F:app/services/spend.py†L243-L286】
- **P1**
  - Remplacer l'API key globale par une authentification multi-acteurs (JWT, rôles) avec rotation et monitoring.【F:app/security.py†L1-L21】
  - Documenter et automatiser le nettoyage des mandats expirés (tâche planifiée ou worker).【F:app/services/mandates.py†L84-L102】
- **P2**
  - Restreindre CORS et ajouter rate limiting pour limiter les abus clés API.【F:app/main.py†L31-L40】
  - Étendre les métriques (Prometheus/OTel) en plus des logs JSON pour une observabilité complète.

**Verdict: NO-GO** — tant que les P0 sur la protection et l'atomicité des mandats ne sont pas corrigés, exposer 10 utilisateurs réels mettrait en péril les fonds.
