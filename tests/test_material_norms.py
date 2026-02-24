from decimal import Decimal
from uuid import uuid4

from app.db import SessionLocal
from app.models.material_catalog_item import MaterialCatalogItem
from app.models.material_norm import MaterialConsumptionNorm
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.material_norms import build_project_material_bom


def _seed_project() -> tuple[int, dict[str, int]]:
    db = SessionLocal()
    try:
        project = Project(name=f"MN-{uuid4().hex[:6]}")
        db.add(project)
        db.flush()
        room = Room(project_id=project.id, name="R1", floor_area_m2=Decimal("10"), wall_area_m2=Decimal("30"), ceiling_area_m2=Decimal("10"), wall_perimeter_m=Decimal("14"), wall_height_m=Decimal("2.5"))
        db.add(room)
        db.flush()
        ids = {}
        for code in ["paint_ceiling", "paint_walls", "cover_floor", "unknown_work"]:
            wt = WorkType(code=f"{code}_{uuid4().hex[:4]}", category="test", unit="m2", name_ru=code, name_sv=code, hours_per_unit=Decimal("1"), base_difficulty_factor=Decimal("1"), is_active=True)
            db.add(wt)
            db.flush()
            ids[code] = wt.id
        db.add_all([
            ProjectWorkItem(project_id=project.id, room_id=room.id, work_type_id=ids["paint_ceiling"], quantity=Decimal("2"), difficulty_factor=Decimal("1"), scope_mode="room"),
            ProjectWorkItem(project_id=project.id, room_id=room.id, work_type_id=ids["paint_walls"], quantity=Decimal("1"), difficulty_factor=Decimal("1"), scope_mode="room"),
            ProjectWorkItem(project_id=project.id, room_id=room.id, work_type_id=ids["cover_floor"], quantity=Decimal("1"), difficulty_factor=Decimal("1"), scope_mode="room"),
            ProjectWorkItem(project_id=project.id, room_id=room.id, work_type_id=ids["unknown_work"], quantity=Decimal("1"), difficulty_factor=Decimal("1"), scope_mode="room"),
        ])
        db.commit()
        return project.id, ids
    finally:
        db.close()


def test_material_norms_engine_core_and_warnings():
    project_id, ids = _seed_project()
    db = SessionLocal()
    try:
        codes = {k: db.get(WorkType, v).code for k, v in ids.items()}
        catalog = MaterialCatalogItem(material_code=f"ceiling_paint_{uuid4().hex[:4]}", name="Ceiling Paint", unit="l", package_size=Decimal("10"), package_unit="l", price_ex_vat=Decimal("980"), vat_rate_pct=Decimal("25"), is_active=True)
        db.add(catalog)
        db.flush()
        db.add_all([
            MaterialConsumptionNorm(material_name="Ceiling Paint", material_category="paint", applies_to_work_type=codes["paint_ceiling"], material_unit="l", work_type_code=codes["paint_ceiling"], basis_type="ceiling_area", consumption_qty=Decimal("3"), per_basis_qty=Decimal("10"), per_basis_unit="m2", consumption_value=Decimal("3"), consumption_unit="per_10_m2", layers_multiplier_enabled=True, waste_percent=Decimal("10"), material_catalog_item_id=catalog.id, active=True),
            MaterialConsumptionNorm(material_name="Wall Paint", material_category="paint", applies_to_work_type=codes["paint_walls"], material_unit="l", work_type_code=codes["paint_walls"], basis_type="wall_area", consumption_qty=Decimal("2"), per_basis_qty=Decimal("10"), per_basis_unit="m2", consumption_value=Decimal("3"), consumption_unit="per_10_m2", layers_multiplier_enabled=False, waste_percent=Decimal("0"), active=True),
            MaterialConsumptionNorm(material_name="Floor Cover", material_category="cover", applies_to_work_type=codes["cover_floor"], material_unit="roll", work_type_code=codes["cover_floor"], basis_type="floor_area", consumption_qty=Decimal("1"), per_basis_qty=Decimal("1"), per_basis_unit="m2", consumption_value=Decimal("1"), consumption_unit="per_1_m2", package_size=Decimal("6"), package_unit="roll", layers_multiplier_enabled=False, waste_percent=Decimal("0"), active=True),
        ])
        db.commit()

        report = build_project_material_bom(project_id, db)
        by_work = {row.work_type_code: row for row in report.line_items}

        assert by_work[codes["paint_ceiling"]].theoretical_qty == Decimal("6.6000")  # ceiling + coats + waste
        assert by_work[codes["paint_walls"]].theoretical_qty == Decimal("6.0000")
        assert by_work[codes["cover_floor"]].theoretical_qty == Decimal("10.0000")
        assert by_work[codes["paint_ceiling"]].purchase_pack_count == 1
        assert by_work[codes["cover_floor"]].purchase_pack_count == 2
        assert any("MISSING_PACKAGING" in w for w in by_work[codes["paint_walls"]].warnings)
        assert any("No material norm configured" in w for w in report.warnings)
    finally:
        db.close()
