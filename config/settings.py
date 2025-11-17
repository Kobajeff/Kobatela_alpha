from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# Définir le chemin de la base de données SQLite
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # Récupère le dossier du fichier actuel
DB_PATH = os.path.join(BASE_DIR, "..", "kobatela.db")  # Stocke la BD dans le dossier du projet

DATABASE_URL = f"sqlite:///{DB_PATH}"  # URL de connexion SQLite

# Créer le moteur SQLAlchemy
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# Créer une session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)



