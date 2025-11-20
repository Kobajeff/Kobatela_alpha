# app/models/__init__.py

# Importez explicitement chaque module qui définit des tables SQLAlchemy.
# Adapte la liste à ton projet réel :
from .user import User
from .escrow import EscrowAgreement, Milestone, Proof, Payment, AllowedPayee
from .psp import PSPWebhookEvent
from .transactions import Transaction
from .usage import UsageRule

# Si tu as d'autres modules/tables, ajoute-les ici.
# Important : ne mets AUCUN code exécutable ici, juste des imports.
from app import models as _app_models  # side-effect: enregistre toutes les tables

# Optionnel: réexporter des symboles utiles si des imports absolus les attendent.
# Adapte cette liste à ton projet réel (mets uniquement ce qui est importé par les tests/app).
try:
    from app.models.user import User
except Exception:
    pass

try:
    from app.models.base import Base
except Exception:
    pass