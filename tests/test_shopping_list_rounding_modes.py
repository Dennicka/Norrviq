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
from app.services.procurement_rounding import ProcurementRoundingPolicy


def test_compute_procurement_plan_rounding_modes():
    db = SessionLocal()
    try:
        project = Project(name=f"P-{uuid4().hex[:6]}")
        work_type = WorkType(
            code=f"paint_walls_rounding_{uuid4().hex[:4]}",
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

        material = Material(code=f"ROUND_CODE_{uuid4().hex[:4]}", name_sv="Paint", name_ru="Краска", unit="L", is_active=True)
        db.add(material)
        db.flush()

        catalog = MaterialCatalogItem(
            material_code=material.code,
            name="Wall Paint 10L",
            unit="L",
            package_size=Decimal("10"),
            package_unit="L",
            price_ex_vat=Decimal("100"),
            supplier_name="Catalog Supplier",
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
                consumption_value=Decimal("1.05"),
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
                material_id=material.id,
                pack_size=Decimal("10"),
                pack_unit="L",
                pack_price_ex_vat=Decimal("100"),
                currency="SEK",
            )
        )
        db.commit()

        ceil_plan = compute_procurement_plan(db, project.id, strategy=ProcurementStrategy.CHEAPEST)
        floor_plan = compute_procurement_plan(
            db,
            project.id,
            strategy=ProcurementStrategy.CHEAPEST,
            policy=ProcurementRoundingPolicy(rounding_mode="FLOOR"),
        )
        ceil_multiple_plan = compute_procurement_plan(
            db,
            project.id,
            strategy=ProcurementStrategy.CHEAPEST,
            policy=ProcurementRoundingPolicy(rounding_mode="CEIL", pack_multiple=2),
        )

        assert ceil_plan.lines[0].packs_needed == Decimal("3")
        assert ceil_plan.lines[0].line_total_cost_ex_vat == Decimal("300.00")

        assert floor_plan.lines[0].packs_needed == Decimal("2")
        assert floor_plan.lines[0].line_total_cost_ex_vat == Decimal("200.00")

        assert ceil_multiple_plan.lines[0].packs_needed == Decimal("4")
        assert ceil_multiple_plan.lines[0].line_total_cost_ex_vat == Decimal("400.00")
    finally:
        db.close()
