"""Add user reference to api_keys"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f00c2d7b2e3b"
down_revision = "5c6b0e0a17b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # Récupère la liste des colonnes de la table api_keys
    columns = [col["name"] for col in inspector.get_columns("api_keys")]

    # Si user_id n'existe pas encore, on l'ajoute
    if "user_id" not in columns:
        op.add_column(
            "api_keys",
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )


def downgrade() -> None:
    # Option simple : si on downgrade, on enlève la colonne si elle existe
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("api_keys")]

    if "user_id" in columns:
        op.drop_column("api_keys", "user_id")


