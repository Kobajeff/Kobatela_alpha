"""Add geofence columns to milestones."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20251105_add_geofence_to_milestones"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(bind, table: str) -> bool:
    return (
        bind.execute(
            sa.text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=:name"
            ),
            {"name": table},
        ).fetchone()
        is not None
    )


def _existing_columns(bind, table: str) -> set[str]:
    return {
        row[1]
        for row in bind.execute(sa.text(f"PRAGMA table_info('{table}')"))
    }


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "milestones"):
        return

    existing = _existing_columns(bind, "milestones")

    if "geofence_lat" not in existing:
        op.add_column("milestones", sa.Column("geofence_lat", sa.Float(), nullable=True))
    if "geofence_lng" not in existing:
        op.add_column("milestones", sa.Column("geofence_lng", sa.Float(), nullable=True))
    if "geofence_radius_m" not in existing:
        op.add_column("milestones", sa.Column("geofence_radius_m", sa.Float(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "milestones"):
        return

    existing = _existing_columns(bind, "milestones")

    if "geofence_radius_m" in existing:
        op.drop_column("milestones", "geofence_radius_m")
    if "geofence_lng" in existing:
        op.drop_column("milestones", "geofence_lng")
    if "geofence_lat" in existing:
        op.drop_column("milestones", "geofence_lat")
