"""add api_keys table (hashed keys with prefix)"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# Révisions Alembic
revision = "8b7e_add_api_keys"
down_revision = "7a4c_unique_active_mandate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # On repart propre : on enlève l'ancienne version de la table si elle existe
    # (elle est créée dans 7a3b_api_keys_table avec une autre structure)
    try:
        op.drop_table("api_keys")
    except Exception:
        # Si la table n'existe pas encore (rare), on ignore l'erreur
        pass

    # Nouvelle table alignée sur app.models.api_key.ApiKey
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("prefix", sa.String(length=12), nullable=False),
        sa.Column("key_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column("scope", sa.String(length=10), nullable=False, server_default="sender"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("prefix", name="uq_api_keys_prefix"),
    )


def downgrade() -> None:
    # Pour les tests on s'en fiche : on supprime la table
    op.drop_table("api_keys")

