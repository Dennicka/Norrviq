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


def test_procurement_converts_required_qty_to_pack_unit_for_pricing():
    db = SessionLocal()
    try:
        project = Project(name=f"P-{uuid4().hex[:6]}")
        work_type = WorkType(
            code=f"paint_units_ok_{uuid4().hex[:4]}",
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

        paint = Material(code=f"PAINT_OK_{uuid4().hex[:4]}", name_sv="Paint", name_ru="Краска", unit="l", is_active=True)
        db.add(paint)
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
        db.add(paint_catalog)
        db.flush()

        db.add(
            MaterialConsumptionNorm(
                active=True,
                applies_to_work_type=work_type.code,
                material_catalog_item_id=paint_catalog.id,
                material_name="Paint",
                material_category="paint",
                material_unit="l",
                surface_type="wall",
                consumption_value=Decimal("0.15"),
                consumption_unit="per_1_m2",
                waste_percent=Decimal("0"),
                layers_multiplier_enabled=False,
                coats_multiplier_mode="none",
            )
        )

        supplier = Supplier(name=f"Supplier-{uuid4().hex[:4]}", is_active=True)
        db.add(supplier)
        db.flush()

        db.add(
            SupplierMaterialPrice(
                supplier_id=supplier.id,
                material_id=paint.id,
                pack_size=Decimal("1000"),
                pack_unit="ml",
                pack_price_ex_vat=Decimal("100"),
                currency="SEK",
            )
        )
        db.commit()

        plan = compute_procurement_plan(db, project.id, strategy=ProcurementStrategy.CHEAPEST)

        line = next(line for line in plan.lines if line.material_id == paint.id)
        assert line.qty == Decimal("1.5000")
        assert line.packs_needed == Decimal("2")
        assert line.line_total_cost_ex_vat == Decimal("200.00")
    finally:
        db.close()
