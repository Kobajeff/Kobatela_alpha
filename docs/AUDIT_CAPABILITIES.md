# Kobatela_alpha — Capability & Stability Audit (2025-11-18)

## A. Synthèse exécutive
- Cycle escrow → preuves → paiements déjà complet : validations EXIF/GPS, géofence et exécution de paiement idempotente s’imbriquent dans `app/services/proofs.py` et `app/services/payments.py`, avec journaux `AuditLog` systématiques.
- RBAC strict par scope (`ApiScope.sender|support|admin`) et API keys hachées : chaque router sensible (`escrow`, `spend`, `transactions`, `proofs`) dépend de `require_scope`, empêchant l’accès invité.
- Intégration IA/OCR défensive : `AI_PROOF_ADVISOR_ENABLED` par défaut à False, appels encapsulés avec fallback `ai_unavailable`, OCR optionnel qui n’écrase pas les métadonnées client.
- Pré-checks documentaires structurés (`compute_document_backend_checks`) comparant montants/devise/IBAN/date/fournisseur avant d’alimenter l’IA.
- Observabilité déjà cadrée : lifespan unique, APScheduler encapsulé, sentry/prometheus optionnels et logging structuré via `app/core/logging`.
- Failles PSP critiques : `verify_signature` référence `hashlib` sans l’importer, cassant la vérification HMAC → la route `/psp/webhook` répond 500 avant toute validation.
- Colonne IA non exploitée : `Proof.ai_risk_level/ai_score/...` ne sont jamais mises à jour, seul `metadata["ai_assessment"]` conserve l’avis IA → aucune persistance requêtable.
- Back-office toujours anonymisé : de nombreuses mutations (`transactions.add_to_allowlist`, `spend.*`, `users.create_user`) auditent avec `actor="admin"/"system"`, empêchant la traçabilité jusqu’à la clé API.
- OCR et IA exposent potentiellement des URL de stockage brutes (preuve non redacted) et des métadonnées sensibles aux providers externes sans masquage additionnel.
- Idempotence incohérente : `/spend/purchases` accepte l’en-tête mais reste optionnel, et aucun verrou `Idempotency-Key` n’est exigé côté router, ouvrant la porte aux doubles achats lors de retries réseau.
- Score de préparation : **74 / 100** pour un staging exposé — GO conditionnel (corriger les P0 PSP/IA/Audit avant pilotes).

## B. Carte des capacités (fonctionnalités actuelles)
### B.1 Couverture fonctionnelle
| Fonctionnalité | Endpoints / modules impliqués | Statut (OK / Partiel / Manquant) | Notes |
| --- | --- | --- | --- |
| Health & métadonnées | `GET /health` (`app/routers/health.py`) | OK | Ping JSON sans auth pour supervision.
| Gestion utilisateurs & API keys | `POST/GET /users`, `POST/GET/DELETE /apikeys` | OK | Génération de clés hachées, audit `CREATE_USER` et `CREATE_API_KEY`.
| Escrow lifecycle complet | `/escrows/*` + `app/services/escrow.py` | OK | Création, dépôts idempotents, transitions livrées/approuvées/rejetées auditées.
| Mandats & dépenses conditionnelles | `/mandates`, `/spend/categories|merchants|allow|purchases|allowed|spend` | Partiel | Autorisations et limites présentes, mais `/spend/purchases` sans idempotence obligatoire.
| Transactions restreintes / allowlist | `/allowlist`, `/certified`, `/transactions` | OK | Alerting antifraude et idempotence sur transactions managées.
| Paiements & PSP | `/payments/execute/{id}`, `/psp/webhook` | Partiel | Exécution payout OK, mais webhook PSP cassé faute d’import `hashlib`.
| Proofs (photo + doc) | `/proofs`, `/proofs/{id}/decision` | OK | Photo → validations hard + auto-approve; docs → review manuel + IA conseil.
| AI Proof Advisor & backend checks | `app/services/ai_proof_advisor.py`, `ai_proof_flags.py`, `document_checks.py` | Partiel | Flags et appels sécurisés, mais champs SQL `ai_*` non renseignés.
| Invoice OCR optionnel | `invoice_ocr.enrich_metadata_with_invoice_ocr` | Partiel | Garde-fous OK mais provider stub (aucune intégration réelle, pas de timeout configurable).

### B.2 Parcours end-to-end supportés aujourd’hui
- **Escrow photo auto-payé** : `/escrows` → `/escrows/{id}/deposit` (idempotent) → `/proofs` (PHOTO + géofence, auto-approve + paiements) → `/payments/execute` si besoin manuel.
- **Mandat d’usage + achats** : `/mandates` (création) → `/spend/allow` (autorisation merchant/catégorie) → `/spend/purchases` (consommation mandat) → `/spend` pour payee dédié.
- **Transactions restreintes** : `/allowlist` + `/certified` pour whitelist → `/transactions` avec `Idempotency-Key` obligatoire, alerting sur tentative non autorisée.
- **PSP settlement** : `/psp/webhook` reçoit les confirmations, persiste `PSPWebhookEvent`, déclenche `finalize_payment_settlement` (bloqué actuellement par NameError).
- **Preuve documentaire IA** : `/proofs` (NON-PHOTO) → enrichissement OCR (si activé) → `compute_document_backend_checks` → `call_ai_proof_advisor` → proof stockée en attente revue.

## C. Inventaire des endpoints
| Méthode | Path | Handler | Auth | Rôles | Modèle requête | Modèle réponse | Codes HTTP |
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
- La configuration centralisée fixe `DEV_API_KEY_ALLOWED = (ENV in {"dev", "local", "dev_local"})`, garantissant que la clé legacy n’est chargée qu’en environnement de développement contrôlé.【F:app/config.py†L11-L24】
- Lorsque cette condition est vraie (ENV=dev seulement), le guard `require_api_key` accepte la clé, crée un audit `LEGACY_API_KEY_USED` et force l’acteur `legacy-apikey` pour éviter la confusion avec des clés nominatives.【F:app/security.py†L42-L83】
- Dans tout autre environnement (staging/prod), le même guard rejette explicitement `DEV_API_KEY` avec le code d’erreur dédié `LEGACY_KEY_FORBIDDEN` (HTTP 401), tout en conservant une trace dans les journaux applicatifs ; aucune requête DB n’est effectuée tant que la clé n’est pas autorisée.【F:app/security.py†L60-L92】【F:app/utils/errors.py†L5-L22】

## G. Observability & ops
- Logging structuré et Sentry optionnel via `app/config.py`; CORS et métriques exposées par la configuration centrale.【F:app/main.py†L52-L78】【F:app/config.py†L32-L71】
- Lifespan unique (`lifespan` context manager) : initialisation DB et scheduler encapsulés sans `@app.on_event` legacy.【F:app/main.py†L23-L74】
- Scheduler optionnel (`SCHEDULER_ENABLED`) avec avertissement clair lorsqu’il est activé hors dev, rappelant la contrainte “un seul runner”.【F:app/main.py†L33-L74】

## H. Risk register (prioritized)
| ID | Component | Risk | Impact | Likelihood | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Spend / Mandates (`app/services/spend.py` L120-L210) | Montants mandats/purchases ne sont jamais normalisés via `Decimal.quantize` avant écriture DB ; des montants à 3 décimales peuvent dériver les compteurs `total_spent`. | Perte de cohérence ledger, litiges financiers | Moyenne | **P0** | Introduire un helper `_to_decimal` commun (cf. `escrow._to_decimal`) et l’appliquer à `payload.amount` avant `_consume_mandate_atomic`, avec test régression.
| R2 | PSP webhook (`app/services/psp_webhooks.py` L13-L43) | `hashlib` n’est pas importé alors qu’il est utilisé pour l’HMAC → NameError avant toute vérification; l’endpoint renvoie 500, aucun évènement PSP traité. | Confirmations PSP ignorées, paiements jamais soldés | Élevée | **P0** | Ajouter `import hashlib`, couvrir par test `test_psp_webhook_invalid_signature` et smoke test sur signature valide.
| R3 | Audit cycle escrow/proofs (multiples services) | `AuditLog` enregistre `actor="client"/"system"`, jamais l’identifiant de clé API/compte réel → traçabilité et non-répudiation impossibles en cas de fraude. | Conformité & forensic bloqués | Élevée | **P0** | Propager `request.state.api_key`/`request.state.user_id` jusqu’aux services, enrichir `AuditLog.actor` (ex : `apikey:{prefix}`) et ajouter tests.
| R4 | Lifecycle/ops (`app/main.py`, scheduler) | Bien que lifespan soit utilisé, `db.create_all()` s’exécute en prod sans garde : risque de divergence avec Alembic (tables créées automatiquement, pas de migrations). | Drift schéma, migrations non appliquées | Moyenne | **P0** | Remplacer `db.create_all()` par vérification Alembic ou limiter à ENV=dev/test via flag; documenter runbook.
| R5 | IA/OCR pipeline (`app/services/proofs.py`, `ai_proof_advisor.py`, `invoice_ocr.py`) | a) Résultats IA stockés uniquement en JSON metadata (les colonnes `ai_*` restent NULL) → aucune requête possible / audit formel. b) `call_ai_proof_advisor` lit `OPENAI_API_KEY` via `os.getenv` sans timeout paramétré ni anonymisation supplémentaire; `invoice_ocr` pourrait publier `storage_url` brute à un provider externe. | Décisions IA non traçables, fuites données si provider compromis | Élevée | **P0** | Persister `ai_*` sur le modèle `Proof` + timestamp, passer par `settings.OPENAI_API_KEY`, tronquer/masquer `storage_url` avant appel, ajouter tests IA/OCR.
| R6 | `/spend/purchases` router (`app/routers/spend.py` L62-L79) | `Idempotency-Key` reste optionnel → retry réseau = double achat consommant le mandat sans contrôle. | Double débit utilisateur | Moyenne | P1 | Rendre l’en-tête obligatoire (même logique que `/spend`), 422 sinon.
| R7 | Confidentialité OCR/IA (metadata + audits) | `AuditLog` pour proofs/transactions stocke `payload.model_dump()` incluant `storage_url`, `supplier_name`, `iban_last4`; les journaux applicatifs peuvent fuiter les données sensibles. | Risque RGPD/fuite PII | Faible | P1 | Filtrer les payloads audités (masquer URL/IBAN), ajouter tests.

## I. IA Proof Advisor, OCR & scoring de risques (section dédiée)
### I.1 Architecture IA
- Flags dans `app/config.py` : `AI_PROOF_ADVISOR_ENABLED=False`, `AI_PROOF_ADVISOR_PROVIDER="openai"`, `AI_PROOF_ADVISOR_MODEL="gpt-5.1-mini"`, `AI_PROOF_TIMEOUT_SECONDS=12`, `OPENAI_API_KEY` optionnelle. `.env.example` documente toutes les variables AI/OCR (IA désactivée par défaut, OCR provider `none`).
- Helpers : `app/services/ai_proof_flags.py` expose `ai_enabled()/ai_model()/ai_provider()/ai_timeout_seconds()` pour isoler la configuration.
- Adaptateur : `app/services/ai_proof_advisor.py` construit `mandate_context`, `backend_checks`, `document_context`, applique un prompt strict et normalise la réponse JSON; exceptions/clé manquante → fallback `ai_unavailable`.

### I.2 Intégration IA dans les flux de proof
- `submit_proof` (PHOTO) : validations EXIF/GPS/géofence → auto-approve possible; si IA activée, appel `call_ai_proof_advisor` et stockage `metadata_payload["ai_assessment"]` (pas de mise à jour des colonnes SQL `ai_*`). En cas d’erreur IA, log + ignore.
- `submit_proof` (NON-PHOTO) : pas d’auto-approve, appel IA purement consultatif après `compute_document_backend_checks`, même stockage metadata. IA OFF = comportement identique à l’existant.
- Garanties : IA ne déclenche jamais d’exception bloquante (try/except large, fallback), AI flag false skippe toute logique.

### I.3 OCR & backend_checks
- OCR : `enrich_metadata_with_invoice_ocr` appelé juste après la copie `metadata_payload` pour les types `PDF/INVOICE/CONTRACT`. OCR activable via `INVOICE_OCR_ENABLED`; stub provider renvoie `{}` si `provider="none"`. Les valeurs normalisées (total/currency/date/iban_last4/ supplier info) n’écrasent jamais un champ déjà présent.
- Backend checks : `compute_document_backend_checks` calcule `amount_check`, `iban_check`, `date_check`, `supplier_check`, renvoie `has_metadata`. Ces signaux sont injectés dans le `context` IA côté non-photo.

### I.4 Risques spécifiques IA/OCR
| ID | Domaine (IA/OCR) | Risque | Impact | Probabilité | Priorité | Fix recommandé |
| --- | --- | --- | --- | --- | --- | --- |
| IA-1 | Persistance IA | Colonnes `Proof.ai_*` jamais alimentées → aucune capacité d’audit / filtrage SQL, tout est dans le JSON metadata mutable. | Investigation impossible, KPIs IA inexistants | Élevée | P0 | Lors de `submit_proof`, copier `ai_result` dans `Proof.ai_*` + `ai_checked_at`, laisser `metadata` pour détails.
| IA-2 | Secret OpenAI | `call_ai_proof_advisor` lit `OPENAI_API_KEY` via `os.getenv` direct, ignorant `settings.OPENAI_API_KEY`, rendant la configuration incohérente (tests/override difficiles). | Mauvaise rotation secrets, plantages silencieux | Moyenne | P1 | Utiliser `settings.OPENAI_API_KEY` et lever une erreur contrôlée si flag ON mais clé absente.
| IA-3 | Données envoyées au provider | `document_context` inclut `storage_url`, `metadata` brute (potentiellement noms bénéficiaires, IBAN masqué). Aucun masquage ni TTL, ni redaction. | Fuite PII/GDPR | Moyenne | P1 | Ajouter un sanitizer avant appel IA : tronquer URL, masquer noms sensibles, limiter metadata aux champs requis.
| OCR-1 | Provider stub | `_call_external_ocr_provider` renvoie `{}` si `provider != none` (pas implémenté) mais log en warning seulement; si activé, on croit OCR actif alors qu’il ne fait rien. | Faux sentiment de contrôle | Faible | P2 | Implémenter provider réel ou désactiver automatiquement si provider inconnu.

## J. Roadmap vers un MVP prêt pour staging
- **Check-list P0 (immédiat)**
  1. Normaliser tous les montants spend/mandate via Decimal quantized (`app/services/spend.py`).
  2. Réparer `app/services/psp_webhooks.verify_signature` (import `hashlib`) + tests signés.
  3. Propager l’identifiant clé API/acteur réel dans toutes les écritures `AuditLog` (escrow/proofs/spend/transactions/users).
  4. Retirer `db.create_all()` du lifespan en prod (flag dev-only) pour forcer Alembic.
  5. Persister les résultats IA dans `Proof.ai_*`, utiliser `settings.OPENAI_API_KEY`, anonymiser les métadonnées envoyées.

- **Check-list P1 (avant pilote élargi)**
  1. Rendre `Idempotency-Key` obligatoire sur `/spend/purchases` et ajouter métriques collisions allowlist.
  2. Renforcer la privacy audits/logs (masquage URL/IBAN, limiter `payload.model_dump()` dans AuditLog).
  3. Ajouter des tests unitaires ciblant IA/OCR : fallback sans clé, enrichissement metadata, backend_checks sur montant/devise/dates.
  4. Documenter/implémenter un provider OCR réel ou désactiver automatiquement le flag tant qu’aucun provider n’est branché.

- **Check-list P2 (améliorations confort/scalabilité)**
  1. Passer APScheduler sur job store partagé / lock distribué avant multi-runner.
  2. Étendre la journalisation pour corréler `request_id`, intégrer dashboards Prometheus (proof pipeline, IA latence).
  3. Ajouter un mode “mock AI” pour tests e2e (simuler `ai_result`).

**Verdict : NO-GO pour un staging avec 10 utilisateurs réels tant que les P0 ci-dessus ne sont pas corrigés (PSP webhook inopérant, absence de persistance IA, montants non normalisés, audits incomplets, runbook migrations ambigu).**

## K. Évidences de vérification
- `python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt` (installation complète des dépendances IA/OpenAI).【da90e3†L1-L44】【b557f3†L1-L24】【c8a33e†L1-L6】
- `alembic upgrade head` → migrations appliquées en chaîne (init → ai_fields → proof_requirements).【39ea3d†L4-L11】【e155ed†L1-L11】
- `alembic current` / `alembic heads` / `alembic history --verbose` confirment le head unique `9c697d41f421`.【83dc3b†L1-L4】【bb8c07†L1-L2】【ea17a3†L1-L48】
- `pytest -q` → `57 passed, 1 skipped, 2 warnings`.【a0642d†L1-L1】【f22524†L1-L1】【cc91c4†L1-L15】
- Commandes grep ayant échoué (documentées) :
  - `rg -n "Numeric(18, 2" -n -g"*.py"` → erreur regex “unclosed group”.【298a55†L1-L5】
  - `rg -n "float(" -n -g"*.py"` → même erreur regex.【c5b666†L1-L5】
- Extraits clés :
  - Flags IA/OCR (`app/config.py` L52-L64).【172a2c†L1-L2】
  - Intégration `proof_requirements` dans `submit_proof`.【4b2f23†L1-L5】
  - Backend checks montant/devise dans `document_checks.py` (L46).【c2285c†L1-L1】
  - Normalisation OCR (`invoice_ocr.py` L1-L75).【f3f69d†L1-L64】
