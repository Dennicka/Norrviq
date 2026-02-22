"""add invoice commercial snapshots

Revision ID: c4d5e6f7a8b9
Revises: b7c8d9e0f1a2
Create Date: 2026-02-22
"""

from alembic import op
import sqlalchemy as sa


revision = "c4d5e6f7a8b9"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("commercial_mode_snapshot", sa.String(length=20), nullable=True))
    op.add_column("invoices", sa.Column("units_snapshot", sa.Text(), nullable=True))
    op.add_column("invoices", sa.Column("rates_snapshot", sa.Text(), nullable=True))
    op.add_column("invoices", sa.Column("subtotal_ex_vat_snapshot", sa.Numeric(12, 2), nullable=True))
    op.add_column("invoices", sa.Column("vat_total_snapshot", sa.Numeric(12, 2), nullable=True))
    op.add_column("invoices", sa.Column("total_inc_vat_snapshot", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "total_inc_vat_snapshot")
    op.drop_column("invoices", "vat_total_snapshot")
    op.drop_column("invoices", "subtotal_ex_vat_snapshot")
    op.drop_column("invoices", "rates_snapshot")
    op.drop_column("invoices", "units_snapshot")
    op.drop_column("invoices", "commercial_mode_snapshot")
