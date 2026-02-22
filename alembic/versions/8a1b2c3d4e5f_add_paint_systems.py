"""add paint systems

Revision ID: 8a1b2c3d4e5f
Revises: 2f8a9c1d4e6b, 6d2a1f9b8c77
Create Date: 2026-02-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8a1b2c3d4e5f"
down_revision: Union[str, Sequence[str], None] = ("2f8a9c1d4e6b", "6d2a1f9b8c77")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


paint_system_surface = sa.Enum("WALLS", "CEILING", "FLOOR", "PAINTABLE_TOTAL", name="paintsystemsurface")


def upgrade() -> None:
    op.create_table(
        "paint_systems",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_paint_systems_name_version"),
    )
    op.create_index(op.f("ix_paint_systems_id"), "paint_systems", ["id"], unique=False)

    paint_system_surface.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "paint_system_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("paint_system_id", sa.Integer(), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("target_surface", paint_system_surface, nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("override_coats_count", sa.Integer(), nullable=True),
        sa.Column("override_waste_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("is_optional", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["paint_system_id"], ["paint_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipe_id"], ["material_recipes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_paint_system_steps_id"), "paint_system_steps", ["id"], unique=False)
    op.create_index(op.f("ix_paint_system_steps_paint_system_id"), "paint_system_steps", ["paint_system_id"], unique=False)

    op.create_table(
        "project_paint_settings",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("default_wall_paint_system_id", sa.Integer(), nullable=True),
        sa.Column("default_ceiling_paint_system_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["default_ceiling_paint_system_id"], ["paint_systems.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["default_wall_paint_system_id"], ["paint_systems.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
    )

    op.create_table(
        "room_paint_settings",
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("wall_paint_system_id", sa.Integer(), nullable=True),
        sa.Column("ceiling_paint_system_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["ceiling_paint_system_id"], ["paint_systems.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["wall_paint_system_id"], ["paint_systems.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("room_id"),
    )


def downgrade() -> None:
    op.drop_table("room_paint_settings")
    op.drop_table("project_paint_settings")
    op.drop_index(op.f("ix_paint_system_steps_paint_system_id"), table_name="paint_system_steps")
    op.drop_index(op.f("ix_paint_system_steps_id"), table_name="paint_system_steps")
    op.drop_table("paint_system_steps")
    op.drop_index(op.f("ix_paint_systems_id"), table_name="paint_systems")
    op.drop_table("paint_systems")
    paint_system_surface.drop(op.get_bind(), checkfirst=True)
