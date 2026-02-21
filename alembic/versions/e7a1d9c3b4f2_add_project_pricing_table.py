"""add project pricing table

Revision ID: e7a1d9c3b4f2
Revises: 8f1c2d3e4b5a
Create Date: 2026-02-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "e7a1d9c3b4f2"
down_revision = "8f1c2d3e4b5a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_pricing",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="HOURLY"),
        sa.Column("hourly_rate_override", sa.Numeric(12, 2), nullable=True),
        sa.Column("fixed_total_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("rate_per_m2", sa.Numeric(12, 2), nullable=True),
        sa.Column("rate_per_room", sa.Numeric(12, 2), nullable=True),
        sa.Column("rate_per_piece", sa.Numeric(12, 2), nullable=True),
        sa.Column("target_margin_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("include_materials", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("include_travel_setup_buffers", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="SEK"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_project_pricing_project_id"),
    )


def downgrade() -> None:
    op.drop_table("project_pricing")
