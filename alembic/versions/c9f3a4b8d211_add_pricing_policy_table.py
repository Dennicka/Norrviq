"""add pricing policy table

Revision ID: c9f3a4b8d211
Revises: bb23cc45dd67
Create Date: 2026-02-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "c9f3a4b8d211"
down_revision = "bb23cc45dd67"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pricing_policy",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("min_margin_pct", sa.Numeric(5, 2), nullable=False, server_default="15.00"),
        sa.Column("min_profit_sek", sa.Numeric(12, 2), nullable=False, server_default="1000.00"),
        sa.Column("min_effective_hourly_ex_vat", sa.Numeric(12, 2), nullable=False, server_default="500.00"),
        sa.Column("block_issue_below_floor", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("warn_only_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("pricing_policy")
