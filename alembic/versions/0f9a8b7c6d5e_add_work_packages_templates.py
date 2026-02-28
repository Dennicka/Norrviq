"""add work package templates

Revision ID: 0f9a8b7c6d5e
Revises: 9f2c4d6e8a10
Create Date: 2026-02-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0f9a8b7c6d5e"
down_revision = "9f2c4d6e8a10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_package_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name_ru", sa.String(length=255), nullable=False),
        sa.Column("name_sv", sa.String(length=255), nullable=False),
        sa.Column("name_en", sa.String(length=255), nullable=False),
        sa.Column("description_ru", sa.Text(), nullable=True),
        sa.Column("description_sv", sa.Text(), nullable=True),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_work_package_templates_code"), "work_package_templates", ["code"], unique=True)
    op.create_index(op.f("ix_work_package_templates_id"), "work_package_templates", ["id"], unique=False)

    op.create_table(
        "work_package_template_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("work_type_code", sa.String(length=64), nullable=False),
        sa.Column("scope_mode", sa.String(length=16), nullable=False, server_default="PROJECT"),
        sa.Column("basis_type", sa.String(length=32), nullable=False, server_default="wall_area_m2"),
        sa.Column("pricing_mode", sa.String(length=20), nullable=False, server_default="HOURLY"),
        sa.Column("coats", sa.Numeric(10, 2), nullable=True),
        sa.Column("layers", sa.Numeric(10, 2), nullable=True),
        sa.Column("norm_hours_per_unit", sa.Numeric(12, 4), nullable=True),
        sa.Column("unit_rate_ex_vat", sa.Numeric(12, 2), nullable=True),
        sa.Column("hourly_rate_ex_vat", sa.Numeric(12, 2), nullable=True),
        sa.Column("fixed_total_ex_vat", sa.Numeric(12, 2), nullable=True),
        sa.Column("difficulty_factor", sa.Numeric(5, 2), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["template_id"], ["work_package_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_work_package_template_items_id"), "work_package_template_items", ["id"], unique=False)
    op.create_index(op.f("ix_work_package_template_items_template_id"), "work_package_template_items", ["template_id"], unique=False)

    op.execute(
        """
        INSERT INTO work_package_templates (id, code, name_ru, name_sv, name_en, description_ru, description_sv, description_en, is_active)
        VALUES
          (1, 'masking_floors_project', 'Укрывка пола (весь проект)', 'Skydda golv (hela projektet)', 'Masking floors (whole project)', 'Стандартная укрывка полов', 'Standard skydd av golv', 'Standard floor masking', true),
          (2, 'paint_ceiling_2coats_project', 'Покраска потолка 2 слоя (весь проект)', 'Måla tak 2 lager (hela projektet)', 'Paint ceiling 2 coats (whole project)', NULL, NULL, NULL, true),
          (3, 'paint_walls_2coats_project', 'Покраска стен 2 слоя (весь проект)', 'Måla väggar 2 lager (hela projektet)', 'Paint walls 2 coats (whole project)', NULL, NULL, NULL, true),
          (4, 'skim_coat_2layers_sanding_project', 'Шпатлёвка 2 слоя + шлифовка (весь проект)', 'Spackla 2 lager + slipning (hela projektet)', 'Skim coat 2 layers + sanding (whole project)', NULL, NULL, NULL, true),
          (5, 'trims_frames_perimeter_project', 'Плинтусы/рамки (периметр)', 'Lister/ramar (omkrets)', 'Trims/frames (perimeter)', NULL, NULL, NULL, true),
          (6, 'openings_count_project', 'Проёмы (по количеству)', 'Öppningar (antal)', 'Openings (count)', NULL, NULL, NULL, true)
        """
    )

    op.execute(
        """
        INSERT INTO work_package_template_items (template_id, work_type_code, scope_mode, basis_type, pricing_mode, coats, layers, sort_order)
        VALUES
          (1, 'MASK_FLOOR', 'PROJECT', 'floor_area_m2', 'HOURLY', NULL, NULL, 1),
          (2, 'PAINT_CEILING', 'PROJECT', 'ceiling_area_m2', 'HOURLY', 2, NULL, 1),
          (3, 'PAINT_WALL', 'PROJECT', 'wall_area_m2', 'HOURLY', 2, NULL, 1),
          (4, 'SKIM_WALL', 'PROJECT', 'wall_area_m2', 'HOURLY', NULL, 2, 1),
          (4, 'SAND_WALL', 'PROJECT', 'wall_area_m2', 'HOURLY', NULL, NULL, 2),
          (5, 'PAINT_TRIM', 'PROJECT', 'perimeter_m', 'HOURLY', NULL, NULL, 1),
          (6, 'OPENINGS', 'PROJECT', 'openings_count', 'HOURLY', NULL, NULL, 1)
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_work_package_template_items_template_id"), table_name="work_package_template_items")
    op.drop_index(op.f("ix_work_package_template_items_id"), table_name="work_package_template_items")
    op.drop_table("work_package_template_items")
    op.drop_index(op.f("ix_work_package_templates_id"), table_name="work_package_templates")
    op.drop_index(op.f("ix_work_package_templates_code"), table_name="work_package_templates")
    op.drop_table("work_package_templates")
