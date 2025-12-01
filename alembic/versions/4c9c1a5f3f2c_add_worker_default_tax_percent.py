"""Add default_tax_percent_for_net to worker

Revision ID: 4c9c1a5f3f2c
Revises: a1b2c3d4e5f6_project_dates_materials
Create Date: 2024-07-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4c9c1a5f3f2c"
down_revision = "9e1b4f3c1234"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workers",
        sa.Column("default_tax_percent_for_net", sa.Numeric(5, 2), nullable=True),
    )


def downgrade():
    op.drop_column("workers", "default_tax_percent_for_net")
