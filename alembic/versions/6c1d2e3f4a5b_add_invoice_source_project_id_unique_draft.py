"""add invoice source project id unique draft

Revision ID: 6c1d2e3f4a5b
Revises: 5d2b7c9e1a11
Create Date: 2026-02-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "6c1d2e3f4a5b"
down_revision = "5d2b7c9e1a11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("source_project_id", sa.Integer(), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_invoices_source_project_id_projects",
            "invoices",
            "projects",
            ["source_project_id"],
            ["id"],
        )
    op.execute(
        "CREATE UNIQUE INDEX uq_invoices_one_active_draft_per_source_project "
        "ON invoices (source_project_id) "
        "WHERE source_project_id IS NOT NULL AND status = 'draft'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_invoices_one_active_draft_per_source_project")
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_invoices_source_project_id_projects", "invoices", type_="foreignkey")
    op.drop_column("invoices", "source_project_id")
