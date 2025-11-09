"""Alembic environment configuration."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# --- Monter le PYTHONPATH sur la racine du projet (…/kobatela_alpha)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --- Imports robustes (nouvelle/ancienne arbo)
try:
    from app.config import get_settings
except Exception:
    # ancien fallback si jamais
    from app.settings import get_settings  # type: ignore

try:
    # si Base est ré-exporté dans app/models/__init__.py
    from app.models import Base  # type: ignore
except Exception:
    # sinon import direct depuis base.py
    from app.models.base import Base  # type: ignore

# ---- Charger la config Alembic
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_url() -> str:
    # 1) priorité à la variable d'env
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url
    # 2) fallback aux settings
    settings = get_settings()
    return getattr(settings, "DATABASE_URL", getattr(settings, "database_url"))

# Cible de métadonnées pour l'autogénération
target_metadata = Base.metadata


def _configure_common_kwargs() -> dict:
    """Options communes à offline/online."""
    return dict(
        target_metadata=target_metadata,
        render_as_batch=True,          # <-- crucial pour SQLite
        compare_type=True,             # détecter les changements de type
        compare_server_default=True,   # détecter les defaults
        literal_binds=True,            # + stable en offline
        dialect_opts={"paramstyle": "named"},
    )


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(url=url, **_configure_common_kwargs())
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {}) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, **_configure_common_kwargs())
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
