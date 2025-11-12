# Kobatela_alpha — Capability & Stability Audit (2025-11-12)

## A. Executive summary
- ✅ Mandats d'usage scellés sur expéditeur/bénéficiaire/devise et décrémentés par mise à jour atomique, supprimant les dérives observées précédemment.【F:app/services/spend.py†L34-L95】【F:app/services/spend.py†L187-L371】【F:tests/test_usage_mandates.py†L207-L272】
- ✅ Traçabilité renforcée : chaque création/consommation/expiration de mandat et chaque achat génèrent un `AuditLog` structuré.【F:app/services/mandates.py†L23-L158】【F:app/services/spend.py†L342-L368】
- ✅ Sécurité monétaire : montants stockés en `Numeric(18,2)` pour achats et mandats, synchronisés avec les migrations récentes.【F:app/models/spend.py†L64-L83】【F:app/models/usage_mandate.py†L33-L66】【F:alembic/versions/6f2a_um_add_total_spent.py†L13-L38】
- ✅ Webhook PSP durci par secret obligatoire, signature HMAC + horodatage et traitement idempotent avec audit des paiements.【F:app/routers/psp.py†L16-L61】【F:app/services/psp_webhooks.py†L20-L144】
- ✅ Suite de tests étendue (31 scénarios) couvrant mandats, dépenses conditionnelles, webhooks et escrows, tous verts.【F:tests/test_usage_mandates.py†L1-L272】【F:tests/test_spend.py†L1-L200】【F:tests/test_psp_webhook.py†L32-L134】【a4b16b†L1-L2】
- ⚠️ P1 — Clé API unique `dev-secret-key` pour l'ensemble du backend : aucune rotation ni cloisonnement des accès.【F:app/config.py†L11-L38】【F:app/security.py†L7-L21】
- ⚠️ P1 — Possibilité d'émettre plusieurs mandats actifs pour le même binôme financeur/bénéficiaire, contournant potentiellement le budget global malgré la sélection du premier mandat trouvé.【F:app/models/usage_mandate.py†L33-L66】【F:app/services/spend.py†L34-L56】
- ⚠️ P2 — Nettoyage des mandats expirés déclenché manuellement via `/mandates/cleanup`, sans ordonnanceur ou tâche planifiée.【F:app/routers/mandates.py†L12-L27】【F:app/services/mandates.py†L120-L145】
- ⚠️ P2 — CORS totalement ouvert (`*`) : acceptable en proto, mais à restreindre avant exposition publique.【F:app/main.py†L20-L47】
- ⚠️ P2 — Index composite récent mais absence d'analyse périodique : prévoir monitoring pour valider l'efficacité sous charge.【F:alembic/versions/6f1f_um_lookup_idx.py†L1-L20】
- Readiness score: **62 / 100** — P0 clos, mais la clé API globale impose un garde-fou avant pilote externe.

## B. Capability map (current, concrete)
### B.1 Feature coverage
| Feature | Implemented endpoints/modules | Status | Notes |
| --- | --- | --- | --- |
| Santé & métadonnées | `GET /health` → `health.healthcheck` | Implémenté | Ping synchrone pour monitoring basique.【F:app/routers/health.py†L4-L11】 |
| Création utilisateurs | `POST /users`, `GET /users/{id}` | Implémenté | CRUD minimal protégé par clé API.【F:app/routers/users.py†L12-L31】 |
| Alertes opérationnelles | `GET /alerts` | Implémenté | Filtre par type/gravité via requête SQL simple.【F:app/routers/alerts.py†L11-L19】 |
| Escrow lifecycle | `/escrows` + service | Implémenté | Gestion de bout en bout avec idempotence dépôts et audit automatique.【F:app/routers/escrow.py†L12-L63】【F:app/services/escrow.py†L40-L149】 |
| Allowlist & certification | `/allowlist`, `/certified` | Implémenté | Déduplication et enregistrement temps réel.【F:app/routers/transactions.py†L27-L64】 |
| Transactions restreintes | `POST /transactions` | Implémenté | Idempotence via header et service dédié.【F:app/routers/transactions.py†L66-L75】【F:app/services/transactions.py†L25-L86】 |
| Mandats d'usage | `/mandates`, `/mandates/cleanup` | Implémenté | Création validée, audit P1 et consommation atomique sur sélection scellée.【F:app/routers/mandates.py†L12-L27】【F:app/services/spend.py†L187-L371】 |
| Spend categories & merchants | `/spend/categories`, `/spend/merchants` | Implémenté | Gestion CRUD avec contrôles d'unicité et journalisation.【F:app/routers/spend.py†L25-L33】【F:app/services/spend.py†L97-L140】 |
| Purchases conditionnels | `POST /spend/purchases` | Implémenté | Vérifie mandat, allowlist ou certification + idempotence clé Idempotency-Key.【F:app/routers/spend.py†L40-L46】【F:app/services/spend.py†L187-L371】 |
| Usage payees & payouts | `/spend/allowed`, `/spend` | Implémenté | Limites quotidiennes/totales et journaux d'audit sur paiements autorisés.【F:app/routers/spend.py†L49-L105】【F:app/services/usage.py†L21-L200】 |
| Proofs & géofence | `/proofs`, `/proofs/{id}/decision` | Implémenté | Analyse EXIF/GPS, hashage et audit sur décisions de preuve.【F:app/routers/proofs.py†L11-L33】【F:app/services/proofs.py†L45-L198】 |
| Paiements sortants & webhooks | `/payments/execute/{id}`, `/psp/webhook` | Implémenté | Exécution interne + webhook HMAC/horodatage et audits de paiements.【F:app/routers/payments.py†L10-L17】【F:app/routers/psp.py†L16-L61】 |

### B.2 Supported end-to-end flows (today)
- Mandat conditionnel diaspora → bénéficiaire : création utilisateurs → `/mandates` → `/spend/purchases` avec sélection scellée, décrément atomique et audit.【F:app/routers/users.py†L12-L31】【F:app/routers/mandates.py†L12-L27】【F:app/services/spend.py†L187-L371】
- Escrow basé sur preuves : `/escrows` → dépôt idempotent → `/proofs` → approbation client avec audit complet.【F:app/routers/escrow.py†L12-L63】【F:app/services/escrow.py†L40-L149】【F:app/services/proofs.py†L139-L185】
- Transaction restreinte : `/allowlist` → `/transactions` (Idempotency-Key) → lecture transaction.【F:app/routers/transactions.py†L27-L88】【F:app/services/transactions.py†L25-L86】
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
| POST | /spend/purchases | `spend.create_purchase` | API key | n/a | `PurchaseCreate` + `Idempotency-Key` | `PurchaseRead` | 201/403/409【F:app/routers/spend.py†L40-L46】【F:app/services/spend.py†L187-L371】 |
| POST | /spend/allowed | `spend.add_allowed_payee` | API key | n/a | `AddPayeeIn` | Payee dict | 201/409【F:app/routers/spend.py†L49-L74】 |
| POST | /spend | `spend.spend` | API key | n/a | `SpendIn` + `Idempotency-Key` | Paiement dict | 200/409【F:app/routers/spend.py†L77-L105】 |
| POST | /proofs | `proofs.submit_proof` | API key | n/a | `ProofCreate` | `ProofRead` | 201/422【F:app/routers/proofs.py†L11-L18】 |
| POST | /proofs/{id}/decision | `proofs.decide_proof` | API key | n/a | `ProofDecision` | `ProofRead` | 200/400【F:app/routers/proofs.py†L21-L33】 |
| POST | /payments/execute/{id} | `payments.execute_payment` | API key | n/a | Path ID | `PaymentRead` | 200/404/409【F:app/routers/payments.py†L10-L17】 |
| POST | /psp/webhook | `psp.psp_webhook` | HMAC secret | n/a | JSON + headers PSP | Ack dict | 200/401/503【F:app/routers/psp.py†L16-L61】 |

## D. Data model & states
| Entity | Key fields | Constraints / Indexes | Notes |
| --- | --- | --- | --- |
| User | `username`, `email`, `is_active` | Unicité username/email | Identité principale des relations.【F:app/models/user.py†L1-L35】 |
| Alert | `type`, `message`, `actor_user_id` | Index type/date | Journal opérationnel.【F:app/models/alert.py†L1-L26】 |
| CertifiedAccount | `user_id`, `level` | Enum + unique `user_id` | Gestion certifications marchands/utilisateurs.【F:app/models/certified.py†L1-L28】 |
| EscrowAgreement | Parties, `amount_total`, `status`, `deadline_at` | Checks + index statut/deadline | Pilote preuves et paiements.【F:app/models/escrow.py†L1-L68】 |
| EscrowDeposit | `escrow_id`, `amount`, `idempotency_key` | Check >0, unique clé | Empêche doublons de dépôt.【F:app/models/escrow.py†L40-L58】 |
| EscrowEvent | `escrow_id`, `kind`, `data_json` | Index multi | Chronologie des actions.【F:app/models/escrow.py†L58-L69】 |
| Milestone | `escrow_id`, `idx`, `amount`, geofence | Unicités + coords | Suivi livraisons conditionnelles.【F:app/models/milestone.py†L1-L47】 |
| Proof | `escrow_id`, `milestone_id`, `sha256`, `status` | Unique hash | Gestion preuves photo/GPS.【F:app/models/proof.py†L1-L24】 |
| Payment | `escrow_id`, `amount`, `psp_ref`, `status` | Check >0, unique ref | Mise à jour via webhooks PSP.【F:app/models/payment.py†L1-L38】 |
| Transaction | `sender_id`, `receiver_id`, `amount`, `idempotency_key` | Unique clé + montants positifs | Transferts autorisés restreints.【F:app/models/transaction.py†L1-L37】 |
| AllowedRecipient | `owner_id`, `recipient_id` | Unique paire | Anti-fraude bénéficiaires.【F:app/models/allowlist.py†L1-L15】 |
| AllowedPayee | `escrow_id`, `payee_ref`, limites | Unique `(escrow_id, payee_ref)` | Gestion limites usage escrow.【F:app/models/allowed_payee.py†L1-L32】 |
| SpendCategory | `code`, `label` | Code unique | Classification dépenses.【F:app/models/spend.py†L1-L21】 |
| Merchant | `name`, `category_id`, `is_certified` | Nom unique, index catégorie | Marchands conditionnels.【F:app/models/spend.py†L24-L53】 |
| AllowedUsage | `owner_id`, `merchant_id/category_id` | Check exclusif + unicités | Règles allowlist hors mandat.【F:app/models/spend.py†L37-L53】 |
| Purchase | `sender_id`, `merchant_id`, `amount`, `idempotency_key` | Checks + index statut | Achats conditionnels en `Decimal`.【F:app/models/spend.py†L64-L83】 |
| UsageMandate | `sender_id`, `beneficiary_id`, `total_amount`, `status`, `total_spent` | Check ≥0 + index composite actif | Mandat diaspora ↔ bénéficiaire avec suivi consommation.【F:app/models/usage_mandate.py†L33-L66】【F:alembic/versions/6f1f_um_lookup_idx.py†L1-L20】 |
| PSPWebhookEvent | `event_id`, `psp_ref`, `kind` | Unique event | Idempotence webhook.【F:app/models/psp_webhook.py†L1-L21】 |
| AuditLog | `actor`, `action`, `entity`, `entity_id` | Timestamps auto | Piste d'audit centrale.【F:app/models/audit.py†L1-L20】 |

**State machines**
- `EscrowStatus` : DRAFT → FUNDED → RELEASABLE → RELEASED/REFUNDED/CANCELLED, piloté avec audit pour chaque mutation.【F:app/models/escrow.py†L12-L20】【F:app/services/escrow.py†L83-L149】
- `UsageMandateStatus` : ACTIVE → CONSUMED/EXPIRED via achat atomique ou nettoyage programmé.【F:app/models/usage_mandate.py†L22-L66】【F:app/services/spend.py†L287-L354】【F:app/services/mandates.py†L120-L145】
- `PurchaseStatus` : COMPLETED par défaut ; rejets réservés à des extensions futures.【F:app/models/spend.py†L56-L83】
- `PaymentStatus` : PENDING → SENT → SETTLED/ERROR selon webhooks PSP.【F:app/models/payment.py†L1-L38】【F:app/services/psp_webhooks.py†L73-L144】
- `MilestoneStatus` : WAITING → PENDING_REVIEW → APPROVED/REJECTED → PAYING/PAID suivant preuves et paiements.【F:app/models/milestone.py†L11-L31】【F:app/services/proofs.py†L139-L185】

## E. Stability results
- `alembic upgrade head` : chaîne de six migrations (init, Decimal, mandats, index, total_spent) appliquée sans erreur.【bf577d†L1-L7】
- `alembic current` : tête unique `6f2a_um_add_total_spent` confirmée.【7f32e7†L1-L4】
- `alembic heads` : aucune branche parallèle, même révision active.【b4c412†L1-L2】
- `pytest -q` : 31 tests réussis (mandats, dépenses, webhooks, escrows).【a4b16b†L1-L2】
- Revue statique : code 100 % synchrone (pas d'I/O bloquante dans des handlers async), sessions SQLAlchemy contrôlées via dépendances FastAPI.【F:app/db.py†L1-L109】【F:tests/conftest.py†L70-L148】
- Idempotence/transactions : helpers centralisés pour achats, dépôts escrow, dépenses usage et webhooks PSP.【F:app/services/idempotency.py†L10-L41】【F:app/services/spend.py†L187-L371】【F:app/services/escrow.py†L62-L149】【F:app/services/psp_webhooks.py†L20-L144】

## F. Security & integrity
- AuthN/AuthZ : dépendance `require_api_key` applique une seule clé API globale, sans scopes ni rotation — risque majeur en cas de fuite.【F:app/config.py†L11-L38】【F:app/security.py†L7-L21】
- Mandats : validation d'existence utilisateurs/marchands, contrôle d'expiration, sélection scellée et rejet des achats concurrents au-delà du plafond.【F:app/services/mandates.py†L68-L118】【F:app/services/spend.py†L187-L313】
- PSP : secret exigé au démarrage, HMAC + horodatage, idempotence et audit des règlements.【F:app/main.py†L20-L38】【F:app/routers/psp.py†L16-L61】【F:app/services/psp_webhooks.py†L20-L144】
- Validation entrées : schémas Pydantic imposent montants positifs, devises ISO, identifiants obligatoires pour mandats/achats.【F:app/schemas/mandates.py†L12-L43】【F:app/schemas/spend.py†L58-L86】
- Preuves : pipeline EXIF/GPS, hash SHA-256 et géofence garantissent intégrité des justificatifs.【F:app/services/proofs.py†L45-L198】
- Audit & logs : logging JSON centralisé, audit couvrant escrows, mandats, paiements et achats conditionnels.【F:app/core/logging.py†L10-L31】【F:app/services/escrow.py†L40-L149】【F:app/services/mandates.py†L23-L158】【F:app/services/spend.py†L342-L368】

## G. Observability & ops
- Lifespan unique : initialisation/fermeture moteur DB et validation des secrets au démarrage.【F:app/main.py†L20-L38】【F:app/db.py†L1-L109】
- CORS permissif (`*`) — acceptable en dev, à resserrer avant exposition publique.【F:app/main.py†L40-L47】
- Migrations cohérentes : historique linéaire jusqu'à l'ajout de `total_spent` avec garde-fous SQLite/Postgres.【F:alembic/versions/baa4932d9a29_0001_init_schema.py†L1-L199】【F:alembic/versions/6f2a_um_add_total_spent.py†L13-L38】
- Nettoyage mandats : endpoint `/mandates/cleanup` dépend d'une exécution manuelle — prévoir cron ou worker.【F:app/routers/mandates.py†L22-L27】【F:app/services/mandates.py†L120-L145】
- Monitoring : logs structurés mais absence de métriques/alerting intégrés (Prometheus/Sentry) à planifier.

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | API security | Clé API globale `dev-secret-key` sans rotation ni scopes → compromission totale si fuite. | Critique | Moyen | P1 | Introduire gestion multi-clés (table API keys), rotation, scopes (sender/support/admin).【F:app/config.py†L11-L38】【F:app/security.py†L7-L21】 |
| R2 | Usage mandates | Plusieurs mandats actifs possibles pour un même binôme expéditeur/bénéficiaire, cumulant les budgets au-delà du plafond attendu. | Élevé | Moyen | P1 | Ajouter contrainte d'unicité partielle (Postgres) ou vérification applicative avant création.【F:app/models/usage_mandate.py†L33-L66】【F:app/services/mandates.py†L68-L118】 |
| R3 | Ops mandats | Expiration dépend d'un appel manuel `/mandates/cleanup` → mandats expirés peuvent rester actifs. | Moyen | Moyen | P2 | Planifier tâche récurrente (cron/worker) ou déclencher expiration lors de chaque création/achat.【F:app/routers/mandates.py†L22-L27】【F:app/services/mandates.py†L120-L145】 |
| R4 | Front-door | CORS `*` autorise toute origine, exposant l'API à des scripts non contrôlés. | Moyen | Élevé | P2 | Restreindre aux domaines de confiance et activer HTTPS/headers de sécurité en staging.【F:app/main.py†L40-L47】 |
| R5 | Observability | Absence de métriques ou d'alertes automatisées limite la détection proactive d'incidents. | Moyen | Moyen | P2 | Intégrer Prometheus/Sentry ou équivalent, exporter métriques sur mandats/achats. |

## I. Roadmap to MVP-ready
- **P0** : ✅ (aucun restant) – mandats scellés + décrément atomique déjà livrés.【F:app/services/spend.py†L34-L95】【F:app/services/spend.py†L187-L371】
- **P1** :
  - Mettre en place gestion multi-clés API + rotation + scopes par rôle.【F:app/security.py†L7-L21】
  - Empêcher la création de mandats actifs doublons (contrainte unique ou contrôle service).【F:app/services/mandates.py†L68-L118】
- **P2** :
  - Automatiser l'expiration (`cron`, worker) et restreindre CORS en préproduction.【F:app/services/mandates.py†L120-L145】【F:app/main.py†L40-L47】
  - Ajouter métriques/alerting (Prometheus/Sentry) pour mandats, webhooks et erreurs critiques.

**Verdict : NO-GO** — Attendre la segmentation des clés API et la prévention des mandats doublons avant d'ouvrir à 10 utilisateurs réels.
