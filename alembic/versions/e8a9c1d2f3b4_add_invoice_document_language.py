"""add invoice document language fields

Revision ID: e8a9c1d2f3b4
Revises: d1e2f3a4b5c6
Create Date: 2026-02-25
"""

from alembic import op
import sqlalchemy as sa


revision = "e8a9c1d2f3b4"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("document_lang", sa.String(length=2), nullable=False, server_default="sv"))
    op.add_column("invoices", sa.Column("issued_lang_snapshot", sa.String(length=2), nullable=True))

    op.execute(
        """
        UPDATE invoices
        SET issued_lang_snapshot = document_lang
        WHERE status = 'issued' AND issued_lang_snapshot IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("invoices", "issued_lang_snapshot")
    op.drop_column("invoices", "document_lang")
