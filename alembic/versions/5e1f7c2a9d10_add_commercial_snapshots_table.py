"""add commercial snapshots table

Revision ID: 5e1f7c2a9d10
Revises: c4d5e6f7a8b9
Create Date: 2026-02-22
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5e1f7c2a9d10"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commercial_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doc_type", sa.String(length=20), nullable=False),
        sa.Column("doc_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("segment", sa.String(length=20), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("m2_basis", sa.String(length=32), nullable=True),
        sa.Column("units_json", sa.Text(), nullable=False),
        sa.Column("rates_json", sa.Text(), nullable=False),
        sa.Column("totals_json", sa.Text(), nullable=False),
        sa.Column("line_items_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doc_type", "doc_id", name="uq_commercial_snapshots_doc"),
    )
    op.create_index(op.f("ix_commercial_snapshots_id"), "commercial_snapshots", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_commercial_snapshots_id"), table_name="commercial_snapshots")
    op.drop_table("commercial_snapshots")
