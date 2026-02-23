from decimal import Decimal
from uuid import uuid4

from app.db import SessionLocal
from app.models.material_actual_entry import ProjectMaterialActualEntry
from app.models.material_norm import MaterialConsumptionNorm
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.material_actuals import compute_materials_plan_vs_actual
from app.services.materials_bom import compute_project_bom


def _seed_project() -> tuple[int, int, int, int]:
    db = SessionLocal()
    try:
        p = Project(name=f"P-{uuid4().hex[:6]}")
        wall = WorkType(code=f"wall_putty_{uuid4().hex[:4]}", category="wall", unit="m2", name_ru="", name_sv="", description_ru=None, description_sv=None, hours_per_unit=Decimal("1"), base_difficulty_factor=Decimal("1"), is_active=True)
        ceil = WorkType(code=f"ceiling_paint_{uuid4().hex[:4]}", category="ceiling", unit="m2", name_ru="", name_sv="", description_ru=None, description_sv=None, hours_per_unit=Decimal("1"), base_difficulty_factor=Decimal("1"), is_active=True)
        floor = WorkType(code=f"floor_protection_{uuid4().hex[:4]}", category="floor", unit="m2", name_ru="", name_sv="", description_ru=None, description_sv=None, hours_per_unit=Decimal("1"), base_difficulty_factor=Decimal("1"), is_active=True)
        db.add_all([p, wall, ceil, floor])
        db.flush()
        r1 = Room(project_id=p.id, name="R1", floor_area_m2=Decimal("10"), wall_area_m2=Decimal("20"), ceiling_area_m2=Decimal("10"))
        r2 = Room(project_id=p.id, name="R2", floor_area_m2=Decimal("5"), wall_area_m2=Decimal("12"), ceiling_area_m2=Decimal("5"))
        db.add_all([r1, r2])
        db.flush()
        db.add_all([
            ProjectWorkItem(project_id=p.id, room_id=r1.id, work_type_id=wall.id, quantity=Decimal("1"), difficulty_factor=Decimal("1")),
            ProjectWorkItem(project_id=p.id, room_id=r1.id, work_type_id=ceil.id, quantity=Decimal("2"), difficulty_factor=Decimal("1")),
            ProjectWorkItem(project_id=p.id, room_id=r1.id, work_type_id=floor.id, quantity=Decimal("1"), difficulty_factor=Decimal("1")),
        ])
        db.commit()
        return p.id, wall.id, ceil.id, floor.id
    finally:
        db.close()


def test_norms_bom_core_cases():
    project_id, wall_id, ceil_id, floor_id = _seed_project()
    db = SessionLocal()
    try:
        wall_code = db.get(WorkType, wall_id).code
        ceil_code = db.get(WorkType, ceil_id).code
        floor_code = db.get(WorkType, floor_id).code
        db.add_all([
            MaterialConsumptionNorm(active=True, material_name="Putty", material_category="putty", applies_to_work_type=wall_code, surface_type="wall", consumption_value=Decimal("1"), consumption_unit="per_10_m2", material_unit="bucket", package_size=Decimal("1"), package_unit="bucket", waste_percent=Decimal("10"), coats_multiplier_mode="none", default_unit_price_sek=Decimal("100")),
            MaterialConsumptionNorm(active=True, material_name="Ceiling paint", material_category="paint", applies_to_work_type=ceil_code, surface_type="ceiling", consumption_value=Decimal("3"), consumption_unit="per_10_m2", material_unit="liter", package_size=Decimal("10"), package_unit="liter", waste_percent=Decimal("0"), coats_multiplier_mode="use_work_coats", default_unit_price_sek=Decimal("20")),
            MaterialConsumptionNorm(active=True, material_name="Floor protection", material_category="protection", applies_to_work_type=floor_code, surface_type="floor", consumption_value=Decimal("1"), consumption_unit="per_1_m2", material_unit="roll", package_size=Decimal("6"), package_unit="roll", waste_percent=Decimal("0"), coats_multiplier_mode="none", default_unit_price_sek=Decimal("50")),
        ])
        db.commit()
        bom = compute_project_bom(db, project_id)
        by_name = {i.name: i for i in bom.items}
        assert by_name["Putty"].qty_required_unit == Decimal("2.2000")  # 20/10*1*1.1
        assert by_name["Ceiling paint"].qty_required_unit == Decimal("6.0000")  # 10/10*3*2 coats
        assert by_name["Floor protection"].qty_required_unit == Decimal("10.0000")
        assert by_name["Floor protection"].packs_count == 2  # ceil(10/6)
        assert by_name["Putty"].cost_ex_vat == Decimal("300.00")

        all_rooms_item = ProjectWorkItem(project_id=project_id, room_id=None, work_type_id=wall_id, quantity=Decimal("1"), difficulty_factor=Decimal("1"))
        db.add(all_rooms_item)
        db.commit()
        bom2 = compute_project_bom(db, project_id)
        putty2 = {i.name: i for i in bom2.items}["Putty"]
        assert putty2.area_m2_used >= Decimal("52.0000")
    finally:
        db.close()


def test_missing_norm_and_actual_variance():
    project_id, wall_id, _ceil_id, _floor_id = _seed_project()
    db = SessionLocal()
    try:
        wall_code = db.get(WorkType, wall_id).code
        db.add(MaterialConsumptionNorm(active=True, material_name="Putty", material_category="putty", applies_to_work_type=wall_code, surface_type="wall", consumption_value=Decimal("1"), consumption_unit="per_10_m2", material_unit="bucket", waste_percent=Decimal("0"), coats_multiplier_mode="none", default_unit_price_sek=Decimal("100")))
        db.add(ProjectMaterialActualEntry(project_id=project_id, material_name="Putty", actual_qty=Decimal("1"), actual_packages=Decimal("1"), actual_cost_sek=Decimal("50")))
        db.commit()
        bom = compute_project_bom(db, project_id)
        assert any("MISSING_NORM" in w for w in bom.warnings)
        report = compute_materials_plan_vs_actual(db, project_id)
        row = next(r for r in report.rows if r.material_name == "Putty")
        assert row.delta_cost == Decimal("-150.00")
    finally:
        db.close()
