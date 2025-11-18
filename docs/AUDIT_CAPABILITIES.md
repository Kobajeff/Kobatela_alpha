# Kobatela_alpha — Capability & Stability Audit (2025-11-20)

## A. Synthèse exécutive
- Chaîne escrow→proof→paiement déjà opérationnelle : validations EXIF/GPS + géofence, auto-approve photo et paiements déclenchés dans `app/services/proofs.py` et `app/services/payments.py` tout en journalisant chaque mutation via `AuditLog`.
- Sécurité par API keys scoped : tous les routers critiques utilisent `require_scope` (sender/support/admin) et propagent l’acteur réel (`apikey:<prefix>`) jusque dans les services et l’audit.
- Stack IA/OCR défensive : flags désactivés par défaut (`AI_PROOF_ADVISOR_ENABLED`, `INVOICE_OCR_ENABLED`), appels OpenAI encapsulés avec fallback sécurisé, contexte sanitizé, et colonnes `Proof.ai_*` alimentées.
- Pré-checks documentaires structurés : `invoice_ocr.enrich_metadata_with_invoice_ocr` normalise les métadonnées puis `compute_document_backend_checks` compare montant/devise/IBAN/date/fournisseur avant d’alimenter l’IA.
- Observabilité solide : lifespan unique (plus de `@app.on_event`), logging structuré, Sentry/Prometheus optionnels, migrations Alembic linéaires vérifiées.
- `/spend/purchases` accepte encore des POST sans `Idempotency-Key` obligatoire, donc un retry réseau peut doubler les achats.
- Webhook PSP dispose d’un seul secret et aucune rotation/alerte : en cas de fuite, un attaquant pourrait forcer des statuts SETTLED.
- `AuditLog` stocke les payloads bruts (URL stockage, IBAN masqué) sans helper d’anonymisation, créant un risque RGPD si les logs sont exportés.
- OCR est toujours un stub : activer le flag donne un faux sentiment de contrôle et aucun test n’assure l’enrichissement réel.
- Les reviewers n’ont aucune obligation d’expliquer les décisions quand `ai_risk_level != "clean"`, ce qui limite la valeur des champs IA persistés.
- Score de préparation : **85 / 100** → GO prudent pour un staging ~10 utilisateurs après correction des P0 listés.

## B. Carte des capacités (fonctionnalités actuelles)
### B.1 Couverture fonctionnelle
| Fonctionnalité | Endpoints / modules impliqués | Statut (OK / Partiel / Manquant) | Notes |
| --- | --- | --- | --- |
| Health & supervision | `GET /health` | OK | Ping JSON sans auth pour monitoring.
| Gestion utilisateurs & API keys | `/users`, `/apikeys` | OK | Création, lecture, audit avec acteur `apikey:<prefix>`.
| Escrow lifecycle | `/escrows/*`, `app/services/escrow.py` | OK | Création, dépôts idempotents, transitions auditées.
| Mandats & dépenses | `/mandates`, `/spend/*` | Partiel | Normalisation Decimal ok mais `Idempotency-Key` optionnelle sur `/spend/purchases`.
| Transactions restreintes | `/allowlist`, `/certified`, `/transactions` | OK | Idempotence obligatoire, vérifications admin.
| Proofs + paiements | `/proofs`, `/payments/execute` | OK | Photo auto-approve, docs en review, paiements auto.
| AI Proof Advisor | `ai_proof_advisor.py`, `proofs.submit_proof` | OK | Flags, sanitation, persistance `ai_*`.
| Invoice OCR | `invoice_ocr.py`, hook `submit_proof` | Partiel | Stub provider, pas de tests fonctionnels.
| Webhook PSP | `/psp/webhook`, `psp_webhooks.py` | OK | Signature HMAC correcte mais pas de rotation/clés secondaires.
| Alertes / cron | `app/services/cron.py`, scheduler optionnel | Partiel | Cron activable via env, mais monitoring limité.

### B.2 Parcours end-to-end supportés aujourd’hui
- **Escrow photo auto-payé** : `/escrows` → `/escrows/{id}/deposit` (clé idempotence) → `/proofs` (PHOTO) → auto-approve + `payments.execute` (si pas déjà SETTLED).
- **Mandat d’usage + achat marchand** : `/mandates` → `/spend/allow` (merchant/catégorie) → `/spend/purchases` (consomme mandat) → audit acteur.
- **Transactions restreintes** : `/allowlist` + `/certified` → `/transactions` (idempotence obligatoire) → `AuditLog` admin.
- **Preuve documentaire IA** : `/proofs` (PDF/INVOICE) → OCR facultatif → `document_checks` → IA conseil → proof en revue avec `ai_*` stockés.
- **PSP settlement** : `/psp/webhook` valide la signature, persiste `PSPWebhookEvent`, met à jour `Payment` SETTLED/ERROR.

## C. Inventaire des endpoints
| Méthode | Path | Handler | Auth | Rôles | Modèle requête | Modèle réponse | Codes HTTP |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | /health | `health.healthcheck` | Aucun | - | - | `{status}` | 200 |
| POST | /users | `users.create_user` | API key | admin/support | `UserCreate` | `UserRead` | 201 / 400 |
| POST | /escrows | `escrow.create_escrow` | API key | sender/admin | `EscrowCreate` | `EscrowRead` | 201 |
| POST | /escrows/{id}/deposit | `escrow.deposit` | API key + optional Idempotency-Key | sender/admin | `EscrowDepositCreate` | `EscrowRead` | 200 / 404 / 409 |
| POST | /proofs | `proofs.submit_proof` | API key | sender | `ProofCreate` | `ProofRead` | 201 / 404 / 422 |
| POST | /proofs/{id}/decision | `proofs.decide_proof` | API key | sender | `ProofDecision` | `ProofRead` | 200 / 400 |
| POST | /spend/purchases | `spend.create_purchase` | API key | sender/admin | `PurchaseCreate` | `PurchaseRead` | 201 / 403 / 409 |
| POST | /spend | `spend.spend` | API key + Idempotency-Key requis | sender/admin | `SpendIn` | dict paiement | 200 / 400 / 409 |
| POST | /transactions | `transactions.post_transaction` | API key + Idempotency-Key | admin | `TransactionCreate` | `TransactionRead` | 201 / 400 / 403 |
| POST | /psp/webhook | `psp.psp_webhook` | Secret PSP | - | JSON brut + headers | `{ok,event_id}` | 200 / 401 / 503 |
| POST | /payments/execute/{id} | `payments.execute_payment` | API key | sender/admin | path id | `PaymentRead` | 200 / 404 / 409 |

## D. Modèle de données & machines à états
- **Entités clés** :
  - `EscrowAgreement`, `EscrowDeposit`, `EscrowEvent` (Numeric(18,2), enums `EscrowStatus`, FK vers users) ; idempotence sur `EscrowDeposit.idempotency_key`.
  - `Milestone` (JSON `proof_requirements`, géofence floats, `MilestoneStatus` enum) et `Proof` (metadata JSON, colonnes IA, status `WAITING/PENDING_REVIEW/APPROVED/REJECTED`).
  - `UsageMandate`, `AllowedUsage`, `Purchase` (montants Numeric, champs `total_spent`, `total_amount`), `AllowedPayee`.
  - `Payment` (`amount`, `status`, `psp_reference`, `idempotency_key`) et `PSPWebhookEvent` (unicité `event_id`).
  - `Transaction`, `AllowedRecipient`, `CertifiedAccount` pour les flux restreints ; `AuditLog`, `ApiKey`, `User` pour sécurité.
- **Machines à états** :
  - Escrow : `DRAFT` → `FUNDED` → `RELEASABLE` → `RELEASED` ou `REFUNDED/CANCELLED` (événements consignés).
  - Proof : `WAITING` (avant soumission) → `PENDING_REVIEW` → `APPROVED/REJECTED`; photos auto-approuvées peuvent déclencher `Payment`.
  - Payment : `PENDING` → `SENT` → `SETTLED/ERROR` selon PSP ou exécution manuelle.
  - Usage mandates : `ACTIVE` avec compteur `total_spent`, mis à jour via `_to_decimal` et cron d’expiration.

## E. Résultats de stabilité
- `pytest -q` → `62 passed, 1 skipped, 2 warnings` (Pydantic Config + coroutine sans plugin).【44348f†L1-L18】
- Tests couvrent : rounding mandates, audit acteurs, PSP webhook (signature valide/invalide), intégration AI fallback/persistance, proofs auto-pay.
- Alembic : `upgrade head`, `current`, `heads`, `history --verbose` exécutés sans erreur ; head unique `9c697d41f421`.【9e9be6†L1-L13】【4b6e38†L1-L4】【ba79ad†L1-L2】【a597ae†L1-L48】
- Revue statique : pas de `@app.on_event`, lifespan unique ; `invoice_ocr` actuellement stub mais garde-fous (try/except, pas d’overwrite). Aucune commande CLI échouée durant l’audit.

## F. Sécurité & intégrité
- **AuthN/Z** : API keys hachées stockées en DB, `require_scope` force sender/support/admin selon route, `DEV_API_KEY` rejeté hors ENV de dev.
- **Validation entrée** : Pydantic impose montants positifs, regex devise, bounds sur geofence ; `submit_proof` nettoie metadata et rejette photos invalides en 422.
- **Fichiers / proofs** : SHA-256 obligatoire, validations EXIF/GPS/géofence, doc proofs restent en review manuelle ; IA jamais bloquante.
- **Secrets/config** : `settings` charge PSP secret, OPENAI, OCR ; `.env.example` documente les flags (AI/OCR off par défaut). Lifespan refuse `create_all` hors dev/local/test.
- **Audit/logging** : `AuditLog` stocke action, acteur, entity_id ; `logger` utilisé pour OCR/AI/PSP/cron. Manque un masque PII avant insertion.

## G. Observabilité & exploitation
- Logging structuré (dictConfig) + Sentry/PROMETHEUS optionnels. Cron (`app/services/cron.py`) activable via `SCHEDULER_ENABLED`.
- Gestion d’erreurs : handlers globaux convertissent exceptions en payload JSON uniforme (`error_response`).
- Déploiement : migrations Alembic obligatoires ; lifespan loggue quand `create_all` est ignoré en staging/prod.
- Pas encore de métriques sur latence IA/OCR ni de dashboard PSP ; à prévoir pour staging.

## H. Registre de risques (priorisé)
| ID | Composant | Risque | Impact | Probabilité | Priorité | Recommandation |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | `/spend/purchases` | Idempotency-Key facultative → retry réseau peut débiter deux fois un mandat. | Double débit, litige client | Moyenne | P0 | Rendre l’en-tête obligatoire (même logique que `/spend`), centraliser la vérification et ajouter un test.
| R2 | `/psp/webhook` | Secret unique sans rotation/alerte. | Escalade : un secret compromis force des statuts SETTLED | Faible-moyenne | P0 | Supporter clé active + clé suivante, alerter quand timestamp proche de la limite, ajouter métrique Prometheus.
| R3 | `AuditLog` | Données sensibles stockées brutes (URLs, IBAN masquée). | Fuite PII lors d’exports/logs | Moyenne | P0 | Introduire `sanitize_payload_for_audit` (masque partiel) et l’utiliser partout avant insert.
| R4 | Lifespan / migrations | `create_all` dépend uniquement de `settings.app_env`; mauvaise conf pourrait créer des tables hors Alembic. | Drift schéma | Faible | P0 | Vérifier `ENV` contre liste blanche + variable explicite `ALLOW_CREATE_ALL`; log d’alerte sinon.
| R5 | IA/OCR | Reviewer peut ignorer `ai_risk_level` + OCR stub; aucune gouvernance sur décisions IA. | Acceptation de preuves douteuses | Moyenne | P0 | Ajouter champ `ai_reviewed_at/ai_reviewed_by`, workflow UI/API imposant justification quand `ai_risk_level != "clean"`; désactiver OCR automatiquement si provider=none.
| R6 | Observabilité IA/OCR | Aucun KPI sur taux d’échec IA/OCR, donc détectabilité faible. | Difficulté à diagnostiquer | Moyenne | P1 | Ajouter métriques Prometheus + logs structurés (latence, résultat).

## I. IA Proof Advisor, OCR & scoring de risques (section dédiée)
### I.1 Architecture IA
- Config : `AI_PROOF_ADVISOR_ENABLED=False`, `AI_PROOF_ADVISOR_MODEL="gpt-5.1-mini"`, timeout configurable (12s). `OPENAI_API_KEY` lu via `settings` et nécessaire uniquement si flag actif. `.env.example` documente toutes les variables IA.
- Modules : `ai_proof_flags.py` (helpers `ai_enabled`, `ai_model`, `ai_timeout_seconds`), `ai_proof_advisor.py` (prompt système complet, builder user message, normalisation résultat, sanitation), `document_checks.py`, `invoice_ocr.py`.

### I.2 Intégration IA dans les flux de proof
- **PHOTO** : validations EXIF/GPS/géofence -> auto-approve => IA appelée (si enabled). Résultat inséré dans `metadata['ai_assessment']` ET colonnes `ai_*` (`risk_level`, `score`, `flags`, `explanation`, `checked_at`). Erreur IA = log + fallback `warning` sans bloquer.
- **NON-PHOTO** : OCR (si activé) enrichit metadata, `compute_document_backend_checks` compare aux `proof_requirements`. IA fonctionne en mode conseil : statut reste PENDING, aucune auto-approve. Résultat stocké identiquement dans metadata + colonnes `ai_*`.
- Preuve finale conserve les champs IA, ce qui permet analytics et audit futur.

### I.3 OCR & backend_checks
- `invoice_ocr.enrich_metadata_with_invoice_ocr` s’exécute dès que `payload.type` ∈ {PDF, INVOICE, CONTRACT}. Si flag off ou erreur provider → metadata inchangée (log warning). Normalise : `invoice_total_amount`, `invoice_currency`, `invoice_date`, `invoice_number`, `supplier_name`, `supplier_country/city`, `iban_last4`, `iban_full_masked`.
- `compute_document_backend_checks` retourne `amount_check`, `iban_check`, `date_check`, `supplier_check` avec diffs absolus/relatifs, correspondance d’IBAN et écart de dates. Ces checks sont injectés dans `ai_context['backend_checks']` pour aider l’IA.

### I.4 Risques spécifiques IA/OCR
| ID | Domaine (IA/OCR) | Risque | Impact | Probabilité | Priorité | Fix recommandé |
| --- | --- | --- | --- | --- | --- | --- |
| IA-1 | Gouvernance | Reviewer ignore `ai_risk_level` faute de workflow obligatoire. | Acceptation d’une preuve suspecte | Moyenne | P0 | Exiger justification + champ `ai_reviewed_at` quand `risk_level != "clean"`.
| IA-2 | Sanitation | Masquage complet du `supplier_name` prive l’IA d’un signal utile. | IA moins pertinente | Faible | P2 | Masquer partiellement (initiales) plutôt que `***masked***`.
| OCR-1 | Provider stub | Flag activé alors qu’aucun provider réel n’est câblé. | Faux sentiment de contrôle | Faible | P2 | Auto-désactivation ou garde forte si provider="none".
| IA-3 | Observabilité | Pas de métrique d’erreur IA/OCR. | Difficulté de debug | Moyenne | P1 | Ajouter compteur Prometheus + logs structurés sur résultat.

## J. Roadmap vers un MVP prêt pour staging
- **P0 (immédiat)**
  1. Rendre `Idempotency-Key` obligatoire sur `/spend/purchases` + tests.
  2. Ajouter `sanitize_payload_for_audit` et l’appliquer avant chaque `AuditLog`.
  3. Supporter rotation du `psp_webhook_secret` + alerte timestamp.
  4. Durcir `create_all` (whitelist d’ENV + flag explicite).
  5. Définir workflow reviewer IA (champ `ai_reviewed_by`/`ai_reviewed_at`, règle métier).

- **P1 (avant pilote élargi)**
  1. Implémenter un provider OCR réel (Mindee/Tabscanner) ou désactiver automatiquement si `provider=none`.
  2. Ajouter métriques Prometheus/Sentry breadcrumb pour IA & OCR.
  3. Mutualiser la vérification d’idempotence dans un helper commun spend/transactions.
  4. Ajouter tests unitaires ciblant `invoice_ocr` et `document_checks` (montants divergents, IBAN mismatch, dates hors plage).

- **P2 (confort / scalabilité)**
  1. Mode “mock AI” pour tests end-to-end hors réseau.
  2. Dashboard reviewer exposant `ai_flags` + diff vs `proof_requirements`.
  3. Notifications Slack/Email sur `risk_level="suspect"`.

**Verdict : GO pour un staging avec 10 utilisateurs réels**, sous réserve d’implémenter la check-list P0 ci-dessus avant ouverture.

## K. Évidences de vérification
- `pytest -q` → `62 passed, 1 skipped, 2 warnings` (Pydantic config + coroutine async).【44348f†L1-L18】
- `alembic upgrade head` exécuté sans erreur, suivi de `alembic current`, `alembic heads`, `alembic history --verbose` montrant la chaîne jusqu’à `9c697d41f421`.【9e9be6†L1-L13】【4b6e38†L1-L4】【ba79ad†L1-L2】【a597ae†L1-L48】
- Config IA/OCR vérifiée dans `app/config.py` et `.env.example` (flags off par défaut). OCR hook visible dans `app/services/proofs.py` lignes 49‑75 ; `document_checks` et `ai_proof_advisor` consultés.
