import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.user import User
from app.models.worktype import WorkType
from app.security import hash_password

client = TestClient(app)


def _ensure_user(email: str, role: str, password: str = "Password#123"):
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == email).first():
            db.add(User(email=email, password_hash=hash_password(password), role=role))
            db.commit()
    finally:
        db.close()


def _login(email: str, password: str = "Password#123"):
    client.get("/logout")
    client.post("/login", data={"username": email, "password": password})


def _seed_project_with_room(name: str = "Room A") -> tuple[int, int]:
    db = SessionLocal()
    try:
        project = Project(name="Bulk Project")
        room = Room(
            project=project,
            name=name,
            floor_area_m2=Decimal("10.00"),
            wall_perimeter_m=Decimal("12.00"),
            wall_height_m=Decimal("2.60"),
            wall_area_m2=Decimal("31.20"),
            ceiling_area_m2=Decimal("10.00"),
            baseboard_length_m=Decimal("12.00"),
            description="Template",
        )
        db.add_all([project, room])
        db.commit()
        db.refresh(project)
        db.refresh(room)
        return project.id, room.id
    finally:
        db.close()


def test_duplicate_room_copies_fields():
    _ensure_user("bulk-admin@example.com", "admin")
    _login("bulk-admin@example.com")
    project_id, room_id = _seed_project_with_room("Kitchen")

    response = client.post(f"/projects/{project_id}/rooms/{room_id}/duplicate", follow_redirects=False)
    assert response.status_code == 303

    db = SessionLocal()
    try:
        rooms = db.query(Room).filter(Room.project_id == project_id).order_by(Room.id.asc()).all()
        assert len(rooms) == 2
        original, duplicate = rooms[0], rooms[1]
        assert duplicate.name.startswith("Kitchen")
        assert duplicate.floor_area_m2 == original.floor_area_m2
        assert duplicate.wall_perimeter_m == original.wall_perimeter_m
        assert duplicate.wall_height_m == original.wall_height_m
        assert duplicate.wall_area_m2 == original.wall_area_m2
        assert duplicate.ceiling_area_m2 == original.ceiling_area_m2
        assert duplicate.baseboard_length_m == original.baseboard_length_m
        assert duplicate.description == original.description
    finally:
        db.close()


def test_duplicate_many_creates_n_rooms():
    _ensure_user("bulk-admin2@example.com", "admin")
    _login("bulk-admin2@example.com")
    project_id, room_id = _seed_project_with_room("Bedroom")

    response = client.post(
        f"/projects/{project_id}/rooms/{room_id}/duplicate_many",
        data={"n": "5", "name_prefix": "Bedroom"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        total = db.query(Room).filter(Room.project_id == project_id).count()
        assert total == 6
    finally:
        db.close()


def test_bulk_create_template_creates_expected_names():
    _ensure_user("bulk-admin3@example.com", "admin")
    _login("bulk-admin3@example.com")
    db = SessionLocal()
    try:
        project = Project(name="Template project")
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/rooms/bulk_create",
        data={
            "name_template": "Room {i}",
            "n": "3",
            "wall_height_m": "2.70",
            "floor_area_m2": "15",
            "wall_perimeter_m": "18",
            "ceiling_area_m2": "15",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        names = [r.name for r in db.query(Room).filter(Room.project_id == project_id).order_by(Room.id.asc()).all()]
        assert names == ["Room 1", "Room 2", "Room 3"]
    finally:
        db.close()


def test_bulk_update_selected_rooms_apply_if_empty():
    _ensure_user("bulk-admin4@example.com", "admin")
    _login("bulk-admin4@example.com")
    db = SessionLocal()
    try:
        project = Project(name="Bulk update project")
        room_1 = Room(project=project, name="R1", wall_height_m=None, description=None)
        room_2 = Room(project=project, name="R2", wall_height_m=Decimal("2.80"), description="locked")
        db.add_all([project, room_1, room_2])
        db.commit()
        db.refresh(project)
        db.refresh(room_1)
        db.refresh(room_2)
        project_id = project.id
        ids = [room_1.id, room_2.id]
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/rooms/bulk_update",
        data={"room_ids": [str(ids[0]), str(ids[1])], "wall_height_m": "2.55", "description": "new", "apply_if_empty": "on"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        r1 = db.get(Room, ids[0])
        r2 = db.get(Room, ids[1])
        assert r1.wall_height_m == Decimal("2.55")
        assert r1.description == "new"
        assert r2.wall_height_m == Decimal("2.80")
        assert r2.description == "locked"
    finally:
        db.close()


def test_bulk_endpoints_require_operator_or_admin():
    _ensure_user("bulk-viewer@example.com", "viewer")
    _login("bulk-viewer@example.com")
    project_id, room_id = _seed_project_with_room("Secure")

    r1 = client.post(f"/projects/{project_id}/rooms/{room_id}/duplicate", follow_redirects=False)
    r2 = client.post(f"/projects/{project_id}/rooms/{room_id}/duplicate_many", data={"n": "2"}, follow_redirects=False)
    r3 = client.post(f"/projects/{project_id}/rooms/bulk_create", data={"name_template": "X {i}", "n": "2"}, follow_redirects=False)
    r4 = client.post(f"/projects/{project_id}/rooms/bulk_update", data={"room_ids": [str(room_id)], "wall_height_m": "2.6"}, follow_redirects=False)

    assert r1.status_code == 403
    assert r2.status_code == 403
    assert r3.status_code == 403
    assert r4.status_code == 403


def test_bulk_create_requires_csrf():
    _ensure_user("bulk-admin5@example.com", "admin")
    _login("bulk-admin5@example.com")
    db = SessionLocal()
    try:
        project = Project(name="CSRF bulk")
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/rooms/bulk_create",
        data={"name_template": "No CSRF {i}", "n": "2"},
        headers={"X-No-Auto-CSRF": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_bulk_operations_do_not_change_existing_work_item_calculations():
    _ensure_user("bulk-admin6@example.com", "admin")
    _login("bulk-admin6@example.com")

    db = SessionLocal()
    try:
        wt = WorkType(
            code=f"BULK-WT-{uuid.uuid4().hex[:8]}",
            category="paint",
            unit="m2",
            name_ru="Тест",
            name_sv="Test",
            description_ru="",
            description_sv="",
            hours_per_unit=Decimal("1.2"),
            base_difficulty_factor=Decimal("1.1"),
        )
        project = Project(name="Regression bulk")
        room = Room(project=project, name="Base room", floor_area_m2=Decimal("10"), wall_height_m=Decimal("2.5"), wall_perimeter_m=Decimal("14"))
        item = ProjectWorkItem(project=project, room=room, work_type=wt, quantity=Decimal("20"), difficulty_factor=Decimal("1.15"))
        db.add_all([wt, project, room, item])
        db.commit()
        db.refresh(project)
        db.refresh(room)
        db.refresh(item)
        project_id = project.id
        room_id = room.id
        before_qty = item.quantity
        before_diff = item.difficulty_factor
    finally:
        db.close()

    client.post(f"/projects/{project_id}/rooms/{room_id}/duplicate", follow_redirects=False)
    client.post(f"/projects/{project_id}/rooms/bulk_create", data={"name_template": "Extra {i}", "n": "2", "wall_height_m": "2.7"}, follow_redirects=False)

    db = SessionLocal()
    try:
        persisted = db.get(ProjectWorkItem, item.id)
        assert persisted.quantity == before_qty
        assert persisted.difficulty_factor == before_diff
    finally:
        db.close()
