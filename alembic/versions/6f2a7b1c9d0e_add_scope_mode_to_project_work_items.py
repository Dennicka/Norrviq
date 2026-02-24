"""add scope mode to project work items

Revision ID: 6f2a7b1c9d0e
Revises: 3c8d2e1f9a0b
Create Date: 2026-02-24 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6f2a7b1c9d0e"
down_revision: Union[str, Sequence[str], None] = "3c8d2e1f9a0b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_work_items",
        sa.Column("scope_mode", sa.String(length=16), nullable=True, server_default="room"),
    )
    op.execute("UPDATE project_work_items SET scope_mode = 'room' WHERE scope_mode IS NULL")
    with op.batch_alter_table("project_work_items") as batch_op:
        batch_op.alter_column("scope_mode", existing_type=sa.String(length=16), nullable=False, server_default="room")


def downgrade() -> None:
    op.drop_column("project_work_items", "scope_mode")
