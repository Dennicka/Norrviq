from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.project import Project
from app.models.room import Room
from app.models.user import User
from app.security import hash_password

client = TestClient(app)


def _ensure_user(email: str, role: str = "admin", password: str = "Password#123") -> None:
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == email).first():
            db.add(User(email=email, password_hash=hash_password(password), role=role))
            db.commit()
    finally:
        db.close()


def _login(email: str, password: str = "Password#123") -> None:
    client.get("/logout")
    client.post("/login", data={"username": email, "password": password})


def _seed_project_with_rooms() -> tuple[int, list[int]]:
    db = SessionLocal()
    try:
        project = Project(name="Wizard fast-entry")
        rooms = [
            Room(project=project, name="Bedroom", length_m=Decimal("4.0"), width_m=Decimal("3.0"), wall_height_m=Decimal("2.5"), openings_area_m2=Decimal("1.2")),
            Room(project=project, name="Kitchen", length_m=Decimal("3.0"), width_m=Decimal("2.5"), wall_height_m=Decimal("2.7"), openings_area_m2=Decimal("0.7")),
            Room(project=project, name="Hall", length_m=Decimal("2.0"), width_m=Decimal("2.0"), wall_height_m=Decimal("2.2"), openings_area_m2=Decimal("0.4")),
        ]
        db.add_all([project, *rooms])
        db.commit()
        db.refresh(project)
        for room in rooms:
            db.refresh(room)
        return project.id, [room.id for room in rooms]
    finally:
        db.close()


def test_rooms_step_renders_table():
    _ensure_user("fast-entry-1@example.com")
    _login("fast-entry-1@example.com")
    project_id, _ = _seed_project_with_rooms()

    response = client.get(f"/projects/{project_id}/wizard?step=rooms&lang=ru")

    assert response.status_code == 200
    assert "Length" in response.text
    assert 'name="length_m_' in response.text


def test_duplicate_room_creates_copy():
    _ensure_user("fast-entry-2@example.com")
    _login("fast-entry-2@example.com")
    project_id, room_ids = _seed_project_with_rooms()

    response = client.post(f"/projects/{project_id}/rooms/{room_ids[0]}/duplicate", follow_redirects=False)
    assert response.status_code == 303

    db = SessionLocal()
    try:
        rooms = db.query(Room).filter(Room.project_id == project_id).order_by(Room.id.asc()).all()
        assert len(rooms) == 4
        original = next(room for room in rooms if room.id == room_ids[0])
        duplicate = rooms[-1]
        assert "copy" in duplicate.name.lower()
        assert duplicate.length_m == original.length_m
        assert duplicate.width_m == original.width_m
        assert duplicate.wall_height_m == original.wall_height_m
        assert duplicate.openings_area_m2 == original.openings_area_m2
    finally:
        db.close()


def test_bulk_set_height_updates_all_rooms():
    _ensure_user("fast-entry-3@example.com")
    _login("fast-entry-3@example.com")
    project_id, _ = _seed_project_with_rooms()

    response = client.post(f"/projects/{project_id}/rooms/bulk-set-height", data={"height_m": "2.6"}, follow_redirects=False)

    assert response.status_code == 303
    db = SessionLocal()
    try:
        heights = [room.wall_height_m for room in db.query(Room).filter(Room.project_id == project_id).all()]
        assert heights
        assert all(height == Decimal("2.6") for height in heights)
    finally:
        db.close()


def test_bulk_update_multiple_rooms():
    _ensure_user("fast-entry-4@example.com")
    _login("fast-entry-4@example.com")
    project_id, room_ids = _seed_project_with_rooms()

    response = client.post(
        f"/projects/{project_id}/rooms/bulk-update",
        data={
            "updates_json": '[{"id": %d, "name": "Bedroom A", "length_m": "4.2", "width_m": "3.4", "height_m": "2.8", "openings_area_m2": "1.1"}, {"id": %d, "name": "Kitchen A", "length_m": "3.3", "width_m": "2.7", "height_m": "2.8", "openings_area_m2": "0.5"}]'
            % (room_ids[0], room_ids[1])
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        first = db.get(Room, room_ids[0])
        second = db.get(Room, room_ids[1])
        assert first.name == "Bedroom A"
        assert first.length_m == Decimal("4.2")
        assert second.name == "Kitchen A"
        assert second.width_m == Decimal("2.7")
        assert second.wall_height_m == Decimal("2.8")
    finally:
        db.close()
