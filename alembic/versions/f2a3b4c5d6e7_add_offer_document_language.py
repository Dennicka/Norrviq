"""add offer document language

Revision ID: f2a3b4c5d6e7
Revises: e8a9c1d2f3b4
Create Date: 2026-02-25 19:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f2a3b4c5d6e7"
down_revision = "e8a9c1d2f3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("offer_document_lang", sa.String(length=2), nullable=False, server_default="sv"))


def downgrade() -> None:
    op.drop_column("projects", "offer_document_lang")
