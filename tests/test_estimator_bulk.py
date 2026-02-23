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
from app.services.estimates import calculate_project_total_hours

client = TestClient(app)
settings = get_settings()


def _login() -> None:
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def _seed_project_with_rooms(*, include_invalid_room: bool = False) -> tuple[int, int]:
    db = SessionLocal()
    try:
        project = Project(name=f"Bulk Project {uuid4().hex[:8]}")
        work_type = WorkType(
            code=f"WT-BULK-{uuid4().hex[:8]}",
            category="floor",
            unit="m2",
            name_ru="Защита пола",
            name_sv="Golvskydd",
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
        return project.id, work_type.id
    finally:
        db.close()


def test_bulk_apply_creates_rows_for_all_valid_rooms():
    _login()
    project_id, work_type_id = _seed_project_with_rooms()

    response = client.post(
        f"/projects/{project_id}/add-work-item",
        data={"work_type_id": str(work_type_id), "apply_to": "all_rooms", "difficulty_factor": "1.0", "comment": "bulk"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        items = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).all()
        assert len(items) == 2
        quantities = sorted(Decimal(str(item.quantity)) for item in items)
        assert quantities == [Decimal("10.00"), Decimal("20.00")]
    finally:
        db.close()


def test_total_hours_aggregation_returns_correct_sum():
    _login()
    project_id, work_type_id = _seed_project_with_rooms()

    client.post(
        f"/projects/{project_id}/add-work-item",
        data={"work_type_id": str(work_type_id), "apply_to": "all_rooms", "difficulty_factor": "1.0"},
        follow_redirects=False,
    )

    db = SessionLocal()
    try:
        total_hours = calculate_project_total_hours(db, project_id)
        assert total_hours == Decimal("45.00")
    finally:
        db.close()


def test_bulk_apply_skips_invalid_geometry_with_partial_success_warning():
    _login()
    project_id, work_type_id = _seed_project_with_rooms(include_invalid_room=True)

    with patch("app.routers.web_projects.add_flash_message") as add_flash:
        response = client.post(
            f"/projects/{project_id}/add-work-item",
            data={"work_type_id": str(work_type_id), "apply_to": "all_rooms", "difficulty_factor": "1.0"},
            follow_redirects=False,
        )

    assert response.status_code == 303

    db = SessionLocal()
    try:
        items = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).all()
        assert len(items) == 2
    finally:
        db.close()

    flash_calls = [call.args for call in add_flash.call_args_list]
    assert any("Invalid" in str(message) and level == "warning" for _, message, level in flash_calls)


def test_single_room_mode_still_works():
    _login()
    project_id, work_type_id = _seed_project_with_rooms()

    db = SessionLocal()
    try:
        room_id = (
            db.query(Room.id)
            .filter(Room.project_id == project_id, Room.name == "R1")
            .scalar()
        )
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/add-work-item",
        data={
            "work_type_id": str(work_type_id),
            "apply_to": "selected_room",
            "room_id": str(room_id),
            "quantity": "5",
            "difficulty_factor": "1.0",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        items = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).all()
        assert len(items) == 1
        assert Decimal(str(items[0].quantity)) == Decimal("5.00")
    finally:
        db.close()
