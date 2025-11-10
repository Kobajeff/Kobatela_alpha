# transactions/models.py  (NOUVELLE VERSION — pont fin)

# Ré-exports vers la vraie définition du modèle et l’engine/session de l’app
from app.models.transaction import Transaction  # <- le SEUL ORM pour la table
from app.models.base import Base

# Option "legacy" si certains imports anciens s'attendent à trouver engine ici
try:
    from app.db import engine as db_engine, SessionLocal
except Exception:  # si ton projet expose l'engine ailleurs
    from config.settings import engine as db_engine  # fallback temporaire
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=db_engine)

def get_session():
    """Alias legacy pour compat tests existants."""
    return SessionLocal()

__all__ = ["Transaction", "Base", "db_engine", "get_session", "SessionLocal"]
