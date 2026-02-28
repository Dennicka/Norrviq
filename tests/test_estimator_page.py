from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.estimator_workspace import build_estimator_workspace


client = TestClient(app)
settings = get_settings()


def _login() -> None:
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def _seed_project() -> tuple[int, int]:
    db = SessionLocal()
    try:
        project = Project(name=f"Estimator page {uuid4().hex[:6]}")
        room1 = Room(project=project, name="Kitchen", floor_area_m2=Decimal("10"), wall_area_m2=Decimal("22"), ceiling_area_m2=Decimal("10"), wall_perimeter_m=Decimal("14"))
        room2 = Room(project=project, name="Hall", floor_area_m2=Decimal("8"), wall_area_m2=Decimal("18"), ceiling_area_m2=Decimal("8"), wall_perimeter_m=Decimal("12"))
        wt = WorkType(code=f"W-{uuid4().hex[:4]}", name_ru="Покраска", name_sv="Paint", category="paint", unit="m2", hours_per_unit=Decimal("0.5"), is_active=True)
        db.add_all([project, room1, room2, wt])
        db.commit()
        return project.id, wt.id
    finally:
        db.close()


def test_estimator_page_get_200_and_contains_title():
    _login()
    project_id, _ = _seed_project()
    response = client.get(f"/projects/{project_id}/estimator")
    assert response.status_code == 200
    assert "Estimator" in response.text or "Смета проекта" in response.text


def test_estimator_items_add_adds_worktype_to_page():
    _login()
    project_id, wt_id = _seed_project()
    add = client.post(f"/projects/{project_id}/estimator/items/add", data={"work_type_id": str(wt_id)}, follow_redirects=False)
    assert add.status_code == 303

    page = client.get(f"/projects/{project_id}/estimator")
    assert "Покраска" in page.text


def test_estimator_recalculate_sets_non_zero_qty_and_hours():
    _login()
    project_id, wt_id = _seed_project()
    client.post(f"/projects/{project_id}/estimator/items/add", data={"work_type_id": str(wt_id)}, follow_redirects=False)
    recalc = client.post(f"/projects/{project_id}/estimator/recalculate", data={}, follow_redirects=False)
    assert recalc.status_code == 303

    db = SessionLocal()
    try:
        item = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).first()
        assert item is not None
        assert Decimal(str(item.calculated_qty or 0)) > 0
        assert Decimal(str(item.calculated_hours or 0)) > 0
    finally:
        db.close()


def test_estimator_apply_mode_changes_active_mode_and_enabled_compare_row():
    _login()
    project_id, wt_id = _seed_project()
    client.post(f"/projects/{project_id}/estimator/items/add", data={"work_type_id": str(wt_id)}, follow_redirects=False)
    apply_mode = client.post(f"/projects/{project_id}/estimator/apply-mode", data={"mode": "PER_M2"}, follow_redirects=False)
    assert apply_mode.status_code == 303

    db = SessionLocal()
    try:
        workspace = build_estimator_workspace(db, project_id, lang="ru")
    finally:
        db.close()

    assert workspace["active_mode"] == "PER_M2"
    per_m2_row = next(row for row in workspace["pricing"]["compare_rows"] if row["mode"] == "PER_M2")
    assert per_m2_row["enabled"] is True


def test_selected_rooms_qty_is_sum_of_selected_rooms():
    _login()
    project_id, wt_id = _seed_project()
    client.post(f"/projects/{project_id}/estimator/items/add", data={"work_type_id": str(wt_id)}, follow_redirects=False)

    db = SessionLocal()
    try:
        rooms = db.query(Room).filter(Room.project_id == project_id).order_by(Room.id).all()
        item = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).first()
        assert item is not None
        update = client.post(
            f"/projects/{project_id}/estimator/items/{item.id}/update",
            data={
                "scope_mode": "SELECTED_ROOMS",
                "basis_type": "floor_area_m2",
                "pricing_mode": "HOURLY",
                "selected_room_ids": [str(rooms[0].id), str(rooms[1].id)],
            },
            follow_redirects=False,
        )
        assert update.status_code == 303
        client.post(f"/projects/{project_id}/estimator/recalculate", data={}, follow_redirects=False)
        db.expire_all()
        updated_item = db.query(ProjectWorkItem).filter(ProjectWorkItem.id == item.id).first()
        assert Decimal(str(updated_item.calculated_qty)) == Decimal("18.00")
    finally:
        db.close()
