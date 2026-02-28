from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.material import Material
from app.models.material_consumption_override import MaterialConsumptionOverride
from app.models.material_norm import MaterialConsumptionNorm
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.estimator_workspace import build_estimator_workspace, calculate_project_total_hours_from_items


client = TestClient(app)
settings = get_settings()


def _login() -> None:
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def _seed_project() -> int:
    db = SessionLocal()
    try:
        project = Project(name=f"Estimator {uuid4().hex[:8]}")
        room1 = Room(project=project, name="R1", floor_area_m2=Decimal("10"), wall_area_m2=Decimal("20"), ceiling_area_m2=Decimal("10"))
        room2 = Room(project=project, name="R2", floor_area_m2=Decimal("12"), wall_area_m2=Decimal("25"), ceiling_area_m2=Decimal("12"))
        wt = WorkType(code=f"PAINT-{uuid4().hex[:6]}", category="wall paint", unit="m2", name_ru="Покраска стен", name_sv="Väggmålning", hours_per_unit=Decimal("0.5"), is_active=True)
        item1 = ProjectWorkItem(project=project, room=room1, work_type=wt, quantity=Decimal("10"), difficulty_factor=Decimal("1"), calculated_hours=Decimal("5"))
        item2 = ProjectWorkItem(project=project, room=room2, work_type=wt, quantity=Decimal("12"), difficulty_factor=Decimal("1"), calculated_hours=Decimal("6"))
        db.add_all([project, room1, room2, wt, item1, item2])
        db.commit()
        db.refresh(project)
        return project.id
    finally:
        db.close()


def test_total_hours_helper_no_double_counting():
    items = [
        ProjectWorkItem(calculated_hours=Decimal("2.5")),
        ProjectWorkItem(calculated_hours=Decimal("3.5")),
        ProjectWorkItem(calculated_hours=Decimal("0")),
    ]
    assert calculate_project_total_hours_from_items(items) == Decimal("6.00")


def test_workspace_builder_returns_geometry_hours_pricing_materials():
    project_id = _seed_project()
    db = SessionLocal()
    try:
        workspace = build_estimator_workspace(db, project_id, lang="ru")
    finally:
        db.close()

    assert workspace["geometry"]["rooms_count"] == 2
    assert workspace["geometry"]["total_floor_area"] == Decimal("22")
    assert workspace["work_items"]["total_hours"] == Decimal("11.00")
    assert {"HOURLY", "FIXED_TOTAL", "PER_M2", "PER_ROOM", "PIECEWORK"}.issubset(set(workspace["pricing"]["scenarios"].keys()))
    assert any(row["mode"] == "FIXED_TOTAL" and row["enabled"] is False for row in workspace["pricing"]["compare_rows"])
    assert "rows" in workspace["materials"]


def test_workspace_builder_override_source_badge_when_override_exists():
    project_id = _seed_project()
    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        item = project.work_items[0]
        material = Material(code=f"MAT-{uuid4().hex[:5]}", name_ru="Краска", name_sv=f"Paint-{uuid4().hex[:5]}", unit="l", default_price_per_unit=Decimal("10"), is_active=True)
        norm = MaterialConsumptionNorm(
            applies_to_work_type=item.work_type.code,
            material_name=material.name_sv,
            material_category="paint",
            material_unit="l",
            consumption_value=Decimal("0.1"),
            consumption_unit="per_m2",
            surface_type="wall",
            active=True,
        )
        db.add_all([material, norm])
        db.flush()
        override = MaterialConsumptionOverride(
            project_id=project.id,
            room_id=item.room_id,
            work_type_id=item.work_type_id,
            material_id=material.id,
            surface_kind="walls",
            unit_basis="m2",
            quantity_per_unit=Decimal("0.2"),
            base_unit_size=Decimal("1"),
            is_active=True,
        )
        db.add(override)
        db.commit()

        workspace = build_estimator_workspace(db, project_id, lang="ru")
    finally:
        db.close()

    assert workspace["materials"]["override_applied"] is True


def test_estimator_route_renders_sections_and_ru_labeling():
    _login()
    project_id = _seed_project()
    response = client.get(f"/projects/{project_id}/estimator?lang=ru")
    assert response.status_code == 200
    assert "Смета проекта" in response.text
    assert "Общие часы" in response.text
    assert "Геометрия" in response.text


def test_estimator_bulk_apply_and_recalc_and_select_pricing():
    _login()
    project_id = _seed_project()
    db = SessionLocal()
    try:
        wt = WorkType(code=f"PRIMER-{uuid4().hex[:5]}", category="primer walls", unit="m2", name_ru="Грунтовка", name_sv="Primer", hours_per_unit=Decimal("0.2"), is_active=True)
        db.add(wt)
        db.commit()
    finally:
        db.close()

    before = client.get(f"/projects/{project_id}/estimator")
    assert before.status_code == 200
    assert "11.00" in before.text

    applied = client.post(f"/projects/{project_id}/estimator/preset", data={"preset": "primer", "scope_mode": "all_rooms", "coats": "1"}, follow_redirects=False)
    assert applied.status_code == 303

    after = client.get(f"/projects/{project_id}/estimator")
    assert after.status_code == 200
    assert "Общие часы" in after.text

    selected = client.post(f"/projects/{project_id}/estimator/select-pricing", data={"mode": "PER_ROOM"}, follow_redirects=False)
    assert selected.status_code == 303

    recalc = client.post(f"/projects/{project_id}/estimator/recalc", data={}, follow_redirects=False)
    assert recalc.status_code == 303



def test_material_override_has_priority_in_materials_plan():
    project_id = _seed_project()
    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        item = project.work_items[0]
        material = Material(code=f"MAT-{uuid4().hex[:5]}", name_ru="Краска", name_sv=f"Paint-{uuid4().hex[:5]}", unit="l", default_price_per_unit=Decimal("10"), is_active=True)
        norm = MaterialConsumptionNorm(
            applies_to_work_type=item.work_type.code,
            material_name=material.name_sv,
            material_category="paint",
            material_unit="l",
            consumption_value=Decimal("0.1"),
            consumption_unit="per_m2",
            surface_type="wall",
            active=True,
        )
        db.add_all([material, norm])
        db.flush()
        project_override = MaterialConsumptionOverride(
            project_id=project.id,
            room_id=None,
            work_type_id=item.work_type_id,
            material_id=material.id,
            surface_kind="walls",
            unit_basis="m2",
            quantity_per_unit=Decimal("0.5"),
            base_unit_size=Decimal("1"),
            is_active=True,
        )
        db.add(project_override)
        db.commit()

        workspace = build_estimator_workspace(db, project_id, lang="ru")
    finally:
        db.close()

    assert workspace["materials"]["rows"]
    assert any(row["source"] in {"project_override", "room_override"} for row in workspace["materials"]["rows"])


def test_workspace_item_invalid_reasons_are_returned():
    project_id = _seed_project()
    db = SessionLocal()
    try:
        item = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).first()
        assert item is not None
        item.scope_mode = "SELECTED_ROOMS"
        item.selected_room_ids_json = None
        item.pricing_mode = "FIXED_TOTAL"
        item.fixed_total_ex_vat = None
        item.norm_hours_per_unit = None
        item.work_type.hours_per_unit = Decimal("0")
        db.add(item)
        db.commit()

        workspace = build_estimator_workspace(db, project_id, lang="ru")
    finally:
        db.close()

    row = workspace["work_items"]["rows"][0]
    assert row["invalid"] is True
    assert "estimator.invalid.no_rooms_selected" in row["reasons"]
