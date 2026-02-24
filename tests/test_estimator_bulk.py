from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.geometry import compute_room_geometry_from_model

client = TestClient(app)
settings = get_settings()


def _login() -> None:
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def _seed_project_with_rooms(*, include_invalid_room: bool = False, category: str = "floor") -> tuple[int, int, int, int]:
    db = SessionLocal()
    try:
        project = Project(name=f"Bulk Project {uuid4().hex[:8]}")
        work_type = WorkType(
            code=f"WT-BULK-{uuid4().hex[:8]}",
            category=category,
            unit="m2",
            name_ru="Тестовая работа",
            name_sv="Testarbete",
            hours_per_unit=Decimal("1.50"),
            base_difficulty_factor=Decimal("1.00"),
            is_active=True,
        )
        room_1 = Room(project=project, name="R1", floor_area_m2=Decimal("10.00"), wall_perimeter_m=Decimal("14.00"), wall_height_m=Decimal("2.50"))
        room_2 = Room(project=project, name="R2", floor_area_m2=Decimal("20.00"), wall_perimeter_m=Decimal("18.00"), wall_height_m=Decimal("2.50"))
        db.add_all([project, work_type, room_1, room_2])
        if include_invalid_room:
            db.add(Room(project=project, name="Invalid", wall_perimeter_m=Decimal("10.00"), wall_height_m=Decimal("2.50")))
        db.commit()
        db.refresh(project)
        db.refresh(work_type)
        db.refresh(room_1)
        db.refresh(room_2)
        return project.id, work_type.id, room_1.id, room_2.id
    finally:
        db.close()


def test_all_rooms_creates_room_level_entries_for_every_room():
    _login()
    project_id, work_type_id, _, _ = _seed_project_with_rooms()

    response = client.post(
        f"/projects/{project_id}/add-work-item",
        data={"work_type_id": str(work_type_id), "scope_mode": "all_rooms", "difficulty_factor": "1.0", "layers": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        items = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).all()
        assert len(items) == 2
        assert all(item.room_id for item in items)
        assert len({item.source_group_ref for item in items}) == 1
    finally:
        db.close()


def test_selected_rooms_creates_entries_only_for_selected_rooms():
    _login()
    project_id, work_type_id, room_1_id, _ = _seed_project_with_rooms()

    response = client.post(
        f"/projects/{project_id}/add-work-item",
        data={
            "work_type_id": str(work_type_id),
            "scope_mode": "selected_rooms",
            "selected_room_ids": [str(room_1_id)],
            "difficulty_factor": "1.0",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        items = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).all()
        assert len(items) == 1
        assert items[0].room_id == room_1_id
    finally:
        db.close()


def test_geometry_basis_uses_matching_room_dimension():
    _login()
    project_id, _, room_1_id, _ = _seed_project_with_rooms(category="wall")

    db = SessionLocal()
    try:
        work_type = WorkType(
            code=f"WT-CEIL-{uuid4().hex[:8]}",
            category="ceiling",
            unit="m2",
            name_ru="Потолок",
            name_sv="Tak",
            hours_per_unit=Decimal("1.00"),
            base_difficulty_factor=Decimal("1.00"),
            is_active=True,
        )
        db.add(work_type)
        db.commit()
        db.refresh(work_type)
    finally:
        db.close()

    client.post(f"/projects/{project_id}/add-work-item", data={"work_type_id": str(work_type.id), "scope_mode": "selected_rooms", "selected_room_ids": [str(room_1_id)], "difficulty_factor": "1.0"}, follow_redirects=False)

    db = SessionLocal()
    try:
        room = db.get(Room, room_1_id)
        item = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).first()
        assert Decimal(str(item.quantity)) == compute_room_geometry_from_model(room).ceiling_area_m2.quantize(Decimal("0.01"))
    finally:
        db.close()


def test_layers_multiplier_is_applied_to_quantity():
    _login()
    project_id, work_type_id, room_1_id, _ = _seed_project_with_rooms(category="ceiling")

    client.post(
        f"/projects/{project_id}/add-work-item",
        data={"work_type_id": str(work_type_id), "scope_mode": "selected_rooms", "selected_room_ids": [str(room_1_id)], "difficulty_factor": "1.0", "layers": "2"},
        follow_redirects=False,
    )

    db = SessionLocal()
    try:
        room = db.get(Room, room_1_id)
        item = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).first()
        expected = (compute_room_geometry_from_model(room).ceiling_area_m2 * Decimal("2")).quantize(Decimal("0.01"))
        assert Decimal(str(item.quantity)) == expected
    finally:
        db.close()


def test_missing_geometry_does_not_crash_and_shows_warning():
    _login()
    project_id, work_type_id, _, _ = _seed_project_with_rooms(include_invalid_room=True)

    with patch("app.routers.web_projects.add_flash_message") as add_flash:
        response = client.post(
            f"/projects/{project_id}/add-work-item",
            data={"work_type_id": str(work_type_id), "scope_mode": "all_rooms", "difficulty_factor": "1.0"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    flash_calls = [call.args for call in add_flash.call_args_list]
    assert any("не хватает размеров" in str(message) and level == "warning" for _, message, level in flash_calls)


def test_selected_rooms_validation_error_when_empty_selection():
    _login()
    project_id, work_type_id, _, _ = _seed_project_with_rooms()

    with patch("app.routers.web_projects.add_flash_message") as add_flash:
        response = client.post(
            f"/projects/{project_id}/add-work-item",
            data={"work_type_id": str(work_type_id), "scope_mode": "selected_rooms", "difficulty_factor": "1.0"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    flash_calls = [call.args for call in add_flash.call_args_list]
    assert any("Выберите хотя бы одно помещение" in str(message) and level == "error" for _, message, level in flash_calls)
