"""update rooms dimensions and metadata

Revision ID: 9e1b4f3c1234
Revises: a1b2c3d4e5f6
Create Date: 2025-02-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "9e1b4f3c1234"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("rooms") as batch_op:
        batch_op.alter_column("walls_area_m2", new_column_name="wall_area_m2")
        batch_op.alter_column("plinth_length_m", new_column_name="baseboard_length_m")
        batch_op.add_column(sa.Column("description", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("wall_perimeter_m", sa.Numeric(10, 2), nullable=True))
        batch_op.add_column(sa.Column("wall_height_m", sa.Numeric(10, 2), nullable=True))
        batch_op.add_column(
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False)
        )
        batch_op.add_column(
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("rooms") as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")
        batch_op.drop_column("wall_height_m")
        batch_op.drop_column("wall_perimeter_m")
        batch_op.drop_column("description")
        batch_op.alter_column("baseboard_length_m", new_column_name="plinth_length_m")
        batch_op.alter_column("wall_area_m2", new_column_name="walls_area_m2")
