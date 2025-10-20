import sys
import os

# Ajouter le dossier racine du projet (kobatela-backend) dans sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)
print("Project root ajouté à sys.path:", project_root)
print("sys.path:", sys.path)

from sqlalchemy import inspect
from config.settings import engine as db_engine

inspector = inspect(db_engine)
tables = inspector.get_table_names()
print("Tables présentes dans la base de données :", tables)