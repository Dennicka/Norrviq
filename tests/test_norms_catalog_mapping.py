from decimal import Decimal
from uuid import uuid4

from app.db import SessionLocal
from app.models.material import Material
from app.models.material_catalog_item import MaterialCatalogItem
from app.models.material_norm import MaterialConsumptionNorm
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.materials_bom import compute_project_bom


def test_norm_bom_uses_material_id_via_catalog_mapping():
    db = SessionLocal()
    try:
        project = Project(name=f"P-{uuid4().hex[:6]}")
        work_type = WorkType(
            code=f"paint_walls_x_{uuid4().hex[:4]}",
            category="wall",
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

        room = Room(project_id=project.id, name="R1", wall_area_m2=Decimal("20"), ceiling_area_m2=Decimal("10"), floor_area_m2=Decimal("10"))
        db.add(room)
        db.flush()

        db.add(ProjectWorkItem(project_id=project.id, room_id=room.id, work_type_id=work_type.id, quantity=Decimal("1"), difficulty_factor=Decimal("1")))

        material = Material(code=f"PAINT_CODE_{uuid4().hex[:4]}", name_sv="Paint", name_ru="Краска", unit="L", is_active=True)
        db.add(material)
        db.flush()

        catalog = MaterialCatalogItem(
            material_code=material.code,
            name="Wall Paint 10L",
            unit="L",
            package_size=Decimal("10"),
            package_unit="L",
            price_ex_vat=Decimal("100"),
            supplier_name="Byggmax",
            is_default_for_material=True,
            is_active=True,
        )
        db.add(catalog)
        db.flush()

        db.add(
            MaterialConsumptionNorm(
                active=True,
                applies_to_work_type=work_type.code,
                material_catalog_item_id=catalog.id,
                material_name="Wall Paint",
                material_category="paint",
                material_unit="L",
                surface_type="wall",
                consumption_value=Decimal("0.1"),
                consumption_unit="per_1_m2",
                waste_percent=Decimal("0"),
                layers_multiplier_enabled=False,
                coats_multiplier_mode="none",
            )
        )
        db.commit()

        report = compute_project_bom(db, project.id)

        assert len(report.items) == 1
        item = report.items[0]
        assert item.material_id == material.id
        assert item.qty_required_unit == Decimal("2.0000")
        assert item.packs_count == 1
    finally:
        db.close()
