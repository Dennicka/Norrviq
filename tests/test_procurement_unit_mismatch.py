from decimal import Decimal
from uuid import uuid4

from app.db import SessionLocal
from app.models.material import Material
from app.models.material_catalog_item import MaterialCatalogItem
from app.models.material_norm import MaterialConsumptionNorm
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.supplier import Supplier
from app.models.supplier_material_price import SupplierMaterialPrice
from app.models.worktype import WorkType
from app.services.materials_bom import ProcurementStrategy, compute_procurement_plan


def test_procurement_incompatible_units_marks_line_unpriced_without_crashing():
    db = SessionLocal()
    try:
        project = Project(name=f"P-{uuid4().hex[:6]}")
        work_type = WorkType(
            code=f"paint_units_{uuid4().hex[:4]}",
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

        room = Room(project_id=project.id, name="R1", wall_area_m2=Decimal("10"), ceiling_area_m2=Decimal("0"), floor_area_m2=Decimal("0"))
        db.add(room)
        db.flush()

        db.add(ProjectWorkItem(project_id=project.id, room_id=room.id, work_type_id=work_type.id, quantity=Decimal("1"), difficulty_factor=Decimal("1")))

        paint = Material(code=f"PAINT_{uuid4().hex[:4]}", name_sv="Paint", name_ru="Краска", unit="l", is_active=True)
        putty = Material(code=f"PUTTY_{uuid4().hex[:4]}", name_sv="Putty", name_ru="Шпаклевка", unit="kg", is_active=True)
        db.add_all([paint, putty])
        db.flush()

        paint_catalog = MaterialCatalogItem(
            material_code=paint.code,
            name="Paint",
            unit="l",
            package_size=Decimal("1"),
            package_unit="l",
            price_ex_vat=Decimal("50"),
            is_default_for_material=True,
            is_active=True,
        )
        putty_catalog = MaterialCatalogItem(
            material_code=putty.code,
            name="Putty",
            unit="kg",
            package_size=Decimal("1"),
            package_unit="kg",
            price_ex_vat=Decimal("20"),
            is_default_for_material=True,
            is_active=True,
        )
        db.add_all([paint_catalog, putty_catalog])
        db.flush()

        db.add_all(
            [
                MaterialConsumptionNorm(
                    active=True,
                    applies_to_work_type=work_type.code,
                    material_catalog_item_id=paint_catalog.id,
                    material_name="Paint",
                    material_category="paint",
                    material_unit="l",
                    surface_type="wall",
                    consumption_value=Decimal("0.5"),
                    consumption_unit="per_1_m2",
                    waste_percent=Decimal("0"),
                    layers_multiplier_enabled=False,
                    coats_multiplier_mode="none",
                ),
                MaterialConsumptionNorm(
                    active=True,
                    applies_to_work_type=work_type.code,
                    material_catalog_item_id=putty_catalog.id,
                    material_name="Putty",
                    material_category="putty",
                    material_unit="kg",
                    surface_type="wall",
                    consumption_value=Decimal("0.2"),
                    consumption_unit="per_1_m2",
                    waste_percent=Decimal("0"),
                    layers_multiplier_enabled=False,
                    coats_multiplier_mode="none",
                ),
            ]
        )

        supplier = Supplier(name=f"Supplier-{uuid4().hex[:4]}", is_active=True)
        db.add(supplier)
        db.flush()

        db.add_all(
            [
                SupplierMaterialPrice(
                    supplier_id=supplier.id,
                    material_id=paint.id,
                    pack_size=Decimal("10"),
                    pack_unit="kg",
                    pack_price_ex_vat=Decimal("100"),
                    currency="SEK",
                ),
                SupplierMaterialPrice(
                    supplier_id=supplier.id,
                    material_id=putty.id,
                    pack_size=Decimal("5"),
                    pack_unit="kg",
                    pack_price_ex_vat=Decimal("50"),
                    currency="SEK",
                ),
            ]
        )
        db.commit()

        plan = compute_procurement_plan(db, project.id, strategy=ProcurementStrategy.CHEAPEST)

        by_material = {line.material_id: line for line in plan.lines}
        paint_line = by_material[paint.id]
        assert paint_line.packs_needed is None
        assert paint_line.unit_price_ex_vat is None
        assert "INCOMPATIBLE_UNITS:l->kg" in paint_line.warnings

        putty_line = by_material[putty.id]
        assert putty_line.packs_needed == Decimal("1")
        assert putty_line.unit_price_ex_vat == Decimal("50")
    finally:
        db.close()
