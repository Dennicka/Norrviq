"""fix work package template work_type_code mappings

Revision ID: 8d4e2f1a6b7c
Revises: 7c1e4f2a9b6d
Create Date: 2026-03-01 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "8d4e2f1a6b7c"
down_revision = "7c1e4f2a9b6d"
branch_labels = None
depends_on = None


CANONICAL_ITEMS: dict[str, list[dict[str, str | int | None]]] = {
    "PKG_PAINT_WALL_2": [
        {"work_type_code": "WALL_PAINT_COAT_1", "basis_type": "wall_area_m2", "sort_order": 1},
        {"work_type_code": "WALL_PAINT_COAT_2", "basis_type": "wall_area_m2", "sort_order": 2},
    ],
    "paint_walls_2coats_project": [
        {"work_type_code": "WALL_PAINT_COAT_1", "basis_type": "wall_area_m2", "sort_order": 1},
        {"work_type_code": "WALL_PAINT_COAT_2", "basis_type": "wall_area_m2", "sort_order": 2},
    ],
    "PKG_PAINT_CEILING_2": [
        {"work_type_code": "CEILING_PAINT_COAT_1", "basis_type": "ceiling_area_m2", "sort_order": 1},
        {"work_type_code": "CEILING_PAINT_COAT_2", "basis_type": "ceiling_area_m2", "sort_order": 2},
    ],
    "paint_ceiling_2coats_project": [
        {"work_type_code": "CEILING_PAINT_COAT_1", "basis_type": "ceiling_area_m2", "sort_order": 1},
        {"work_type_code": "CEILING_PAINT_COAT_2", "basis_type": "ceiling_area_m2", "sort_order": 2},
    ],
    "PKG_SPACKLE_WALL_2": [
        {"work_type_code": "WALL_SPACKLE_LAYER_1", "basis_type": "wall_area_m2", "sort_order": 1},
        {"work_type_code": "WALL_SPACKLE_LAYER_2", "basis_type": "wall_area_m2", "sort_order": 2},
        {"work_type_code": "WALL_SANDING", "basis_type": "wall_area_m2", "sort_order": 3},
    ],
    "skim_coat_2layers_sanding_project": [
        {"work_type_code": "WALL_SPACKLE_LAYER_1", "basis_type": "wall_area_m2", "sort_order": 1},
        {"work_type_code": "WALL_SPACKLE_LAYER_2", "basis_type": "wall_area_m2", "sort_order": 2},
        {"work_type_code": "WALL_SANDING", "basis_type": "wall_area_m2", "sort_order": 3},
    ],
    "PKG_SPACKLE_WALL_1": [
        {"work_type_code": "WALL_SPACKLE_LAYER_1", "basis_type": "wall_area_m2", "sort_order": 1},
    ],
    "PKG_SANDING_WALL": [
        {"work_type_code": "WALL_SANDING", "basis_type": "wall_area_m2", "sort_order": 1},
    ],
    "PKG_PRIMER_WALL": [
        {"work_type_code": "WALL_PAINT_PRIMER", "basis_type": "wall_area_m2", "sort_order": 1},
    ],
    "PKG_PREP_FLOOR_COVER": [
        {"work_type_code": "COVER_FLOOR_PAPER", "basis_type": "floor_area_m2", "sort_order": 1},
    ],
    "masking_floors_project": [
        {"work_type_code": "COVER_FLOOR_PAPER", "basis_type": "floor_area_m2", "sort_order": 1},
    ],
    "PKG_MASKING": [
        {"work_type_code": "MASKING_TAPE", "basis_type": "perimeter_m", "sort_order": 1},
    ],
    "PKG_BASEBOARD": [
        {"work_type_code": "BASEBOARD_PAINT", "basis_type": "perimeter_m", "sort_order": 1},
    ],
    "trims_frames_perimeter_project": [
        {"work_type_code": "BASEBOARD_PAINT", "basis_type": "perimeter_m", "sort_order": 1},
    ],
    "openings_count_project": [
        {"work_type_code": "DOOR_PAINT_ONE_SIDE", "basis_type": "openings_count", "sort_order": 1},
    ],
}


def upgrade() -> None:
    conn = op.get_bind()
    templates = conn.execute(
        sa.text(
            "SELECT id, code FROM work_package_templates WHERE code IN :codes"
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": list(CANONICAL_ITEMS.keys())},
    ).mappings()

    for row in templates:
        template_id = int(row["id"])
        template_code = str(row["code"])
        conn.execute(
            sa.text("DELETE FROM work_package_template_items WHERE template_id = :template_id"),
            {"template_id": template_id},
        )
        for item in CANONICAL_ITEMS[template_code]:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO work_package_template_items (
                        template_id,
                        work_type_code,
                        scope_mode,
                        basis_type,
                        pricing_mode,
                        coats,
                        layers,
                        sort_order,
                        difficulty_factor
                    )
                    VALUES (
                        :template_id,
                        :work_type_code,
                        'PROJECT',
                        :basis_type,
                        'HOURLY',
                        NULL,
                        NULL,
                        :sort_order,
                        1
                    )
                    """
                ),
                {
                    "template_id": template_id,
                    "work_type_code": item["work_type_code"],
                    "basis_type": item["basis_type"],
                    "sort_order": int(item["sort_order"]),
                },
            )


def downgrade() -> None:
    # Data-fix only migration; downgrade intentionally does nothing.
    return None
