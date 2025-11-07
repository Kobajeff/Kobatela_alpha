"""Alembic environment configuration."""
from __future__ import annotations

import os
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context



PROJECT_ROOT = Path(__file__).resolve().parents[1]  # .../kobatela_alpha
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# ✅ nouveaux chemins après refactor core/
from app.core.config import get_settings
from app.core.database import Base


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)
    


def get_url() -> str:
    # 1) priorité à la variable d'env
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url
    # 2) fallback aux settings (tolérant UPPER/lower)
    settings = get_settings()
    return getattr(settings, "DATABASE_URL", getattr(settings, "database_url"))


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


# ✅ Ne pas oublier la branche online
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
