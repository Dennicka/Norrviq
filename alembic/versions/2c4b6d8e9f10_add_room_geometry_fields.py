"""add room geometry fields

Revision ID: 2c4b6d8e9f10
Revises: 8d1a2b3c4d5e
Create Date: 2026-02-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2c4b6d8e9f10"
down_revision = "8d1a2b3c4d5e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rooms", sa.Column("length_m", sa.Numeric(10, 2), nullable=True))
    op.add_column("rooms", sa.Column("width_m", sa.Numeric(10, 2), nullable=True))
    op.add_column("rooms", sa.Column("openings_area_m2", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("rooms", "openings_area_m2")
    op.drop_column("rooms", "width_m")
    op.drop_column("rooms", "length_m")
