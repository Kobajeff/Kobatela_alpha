"""add gov public tables

Revision ID: 3d7e23f4c1e9
Revises: 1f07c9ed5f3d
Create Date: 2025-02-25 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3d7e23f4c1e9"
down_revision = "1f07c9ed5f3d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    gov_entity_type = sa.Enum("ministry", "agency", "ong", "other", name="goventitytype", native_enum=False)
    bind = op.get_bind()
    gov_entity_type.create(bind, checkfirst=True)

    op.create_table(
        "gov_entities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("type", gov_entity_type, nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
    )

    op.create_table(
        "gov_projects",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("gov_entity_id", sa.Integer(), sa.ForeignKey("gov_entities.id"), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("project_type", sa.String(length=100), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("execution_mode", sa.String(length=20), nullable=False, server_default="basic"),
        sa.Column("domain", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
    )

    op.create_table(
        "gov_project_mandates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("gov_project_id", sa.Integer(), sa.ForeignKey("gov_projects.id"), nullable=False),
        sa.Column("escrow_id", sa.Integer(), sa.ForeignKey("escrow_agreements.id"), nullable=False),
    )

    op.create_table(
        "gov_project_managers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("gov_project_id", sa.Integer(), sa.ForeignKey("gov_projects.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_table("gov_project_managers")
    op.drop_table("gov_project_mandates")
    op.drop_table("gov_projects")
    op.drop_table("gov_entities")

    gov_entity_type = sa.Enum("ministry", "agency", "ong", "other", name="goventitytype", native_enum=False)
    bind = op.get_bind()
    gov_entity_type.drop(bind, checkfirst=True)
