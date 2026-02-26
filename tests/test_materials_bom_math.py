from decimal import Decimal
from uuid import uuid4

from app.db import SessionLocal
from app.models.material_norm import MaterialConsumptionNorm
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.materials_bom import compute_project_bom


def test_material_bom_math_layers_and_waste():
    db = SessionLocal()
    try:
        project = Project(name=f"Math-{uuid4().hex[:6]}")
        work_type = WorkType(
            code=f"ceil-{uuid4().hex[:4]}",
            category="ceiling",
            unit="m2",
            name_ru="",
            name_sv="",
            description_ru=None,
            description_sv=None,
            hours_per_unit=Decimal("1"),
            base_difficulty_factor=Decimal("1"),
            is_active=True,
        )
        db.add_all([project, work_type])
        db.flush()
        room = Room(project_id=project.id, name="R", ceiling_area_m2=Decimal("20"), floor_area_m2=Decimal("20"), wall_area_m2=Decimal("40"))
        db.add(room)
        db.flush()
        db.add(ProjectWorkItem(project_id=project.id, room_id=room.id, work_type_id=work_type.id, quantity=Decimal("2"), difficulty_factor=Decimal("1")))
        db.add(
            MaterialConsumptionNorm(
                active=True,
                is_active=True,
                material_name="Ceiling paint",
                material_category="paint",
                applies_to_work_type=work_type.code,
                work_type_code=work_type.code,
                basis_type="ceiling_area_m2",
                surface_type="ceiling",
                consumption_qty=Decimal("3"),
                per_basis_qty=Decimal("10"),
                layers_multiplier_enabled=True,
                waste_factor_pct=Decimal("10"),
                consumption_value=Decimal("3"),
                consumption_unit="per_10_m2",
                material_unit="L",
                waste_percent=Decimal("10"),
            )
        )
        db.commit()

        bom = compute_project_bom(db, project.id)
        line = next(item for item in bom.items if item.name == "Ceiling paint")
        assert line.qty_required_unit == Decimal("13.2000")
    finally:
        db.close()
