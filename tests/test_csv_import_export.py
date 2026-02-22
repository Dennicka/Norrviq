import io
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


def test_export_rooms_csv_has_headers_and_rows():
    _ensure_user("csv-admin@example.com", "admin")
    _login("csv-admin@example.com")
    db = SessionLocal()
    try:
        project = Project(name="CSV export rooms")
        room = Room(project=project, name="Kitchen", floor_area_m2=Decimal("10.00"), wall_perimeter_m=Decimal("12.00"), wall_height_m=Decimal("2.60"))
        db.add_all([project, room])
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()

    response = client.get(f"/projects/{project_id}/rooms/export.csv")
    assert response.status_code == 200
    lines = response.text.strip().splitlines()
    assert lines[0] == "room_id,name,floor_area_m2,perimeter_m,ceiling_height_m,notes"
    assert "Kitchen" in lines[1]


def test_import_rooms_preview_detects_errors():
    _ensure_user("csv-admin2@example.com", "admin")
    _login("csv-admin2@example.com")
    db = SessionLocal()
    try:
        project = Project(name="CSV preview")
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()

    payload = "room_id,name,floor_area_m2,perimeter_m,ceiling_height_m,notes\n,Room 1,-1,10,2.6,bad\n"
    response = client.post(
        f"/projects/{project_id}/import/rooms/preview",
        files={"file": ("rooms.csv", io.BytesIO(payload.encode("utf-8")), "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["block_count"] >= 1


def test_import_rooms_apply_creates_and_updates_atomically():
    _ensure_user("csv-admin3@example.com", "admin")
    _login("csv-admin3@example.com")
    db = SessionLocal()
    try:
        project = Project(name="CSV apply")
        room = Room(project=project, name="Old", floor_area_m2=Decimal("5"), wall_perimeter_m=Decimal("9"), wall_height_m=Decimal("2.4"))
        db.add_all([project, room])
        db.commit()
        db.refresh(project)
        db.refresh(room)
        project_id = project.id
        room_id = room.id
    finally:
        db.close()

    csv_data = f"room_id,name,floor_area_m2,perimeter_m,ceiling_height_m,notes\n{room_id},Old updated,6,10,2.5,ok\n,New room,8,12,2.7,new\n"
    preview = client.post(
        f"/projects/{project_id}/import/rooms/preview",
        files={"file": ("rooms.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")},
    )
    token = preview.json()["preview_token"]
    apply_response = client.post(f"/projects/{project_id}/import/apply", data={"preview_token": token})
    assert apply_response.status_code == 200

    db = SessionLocal()
    try:
        rooms = db.query(Room).filter(Room.project_id == project_id).order_by(Room.id.asc()).all()
        assert len(rooms) == 2
        assert rooms[0].name == "Old updated"
        assert rooms[1].name == "New room"
    finally:
        db.close()


def test_import_workitems_requires_existing_room_and_worktype():
    _ensure_user("csv-admin4@example.com", "admin")
    _login("csv-admin4@example.com")
    db = SessionLocal()
    try:
        project = Project(name="CSV wi")
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()

    csv_data = "item_id,room_id,room_name,work_type_code,work_type_name,quantity,unit,notes\n,,Missing,UNKNOWN,,1,m2,bad\n"
    preview = client.post(
        f"/projects/{project_id}/import/work-items/preview",
        files={"file": ("workitems.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")},
    )
    assert preview.status_code == 200
    assert preview.json()["block_count"] >= 1


def test_import_rejects_cross_project_ids():
    _ensure_user("csv-admin5@example.com", "admin")
    _login("csv-admin5@example.com")
    db = SessionLocal()
    try:
        project1 = Project(name="P1")
        project2 = Project(name="P2")
        room2 = Room(project=project2, name="Other", floor_area_m2=Decimal("5"), wall_perimeter_m=Decimal("8"), wall_height_m=Decimal("2.5"))
        wt = WorkType(
            code=f"CSV-WT-{uuid.uuid4().hex[:8]}",
            category="paint",
            unit="m2",
            name_ru="Покраска",
            name_sv="Paint",
            description_ru="",
            description_sv="",
            hours_per_unit=Decimal("1.0"),
            base_difficulty_factor=Decimal("1.0"),
        )
        item = ProjectWorkItem(project=project2, room=room2, work_type=wt, quantity=Decimal("2"), difficulty_factor=Decimal("1"))
        db.add_all([project1, project2, room2, wt, item])
        db.commit()
        db.refresh(project1)
        db.refresh(item)
        project1_id = project1.id
        foreign_item_id = item.id
    finally:
        db.close()

    csv_data = f"item_id,room_id,room_name,work_type_code,work_type_name,quantity,unit,notes\n{foreign_item_id},,,,{''},2,m2,attempt\n"
    preview = client.post(
        f"/projects/{project1_id}/import/work-items/preview",
        files={"file": ("workitems.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")},
    )
    assert preview.status_code == 200
    assert preview.json()["block_count"] >= 1


def test_import_requires_role_and_csrf():
    _ensure_user("csv-viewer@example.com", "viewer")
    _login("csv-viewer@example.com")
    db = SessionLocal()
    try:
        project = Project(name="CSV secure")
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()

    payload = "room_id,name,floor_area_m2,perimeter_m,ceiling_height_m,notes\n,Room 1,5,10,2.5,ok\n"
    forbidden = client.post(
        f"/projects/{project_id}/import/rooms/preview",
        files={"file": ("rooms.csv", io.BytesIO(payload.encode("utf-8")), "text/csv")},
    )
    assert forbidden.status_code == 403

    _ensure_user("csv-admin6@example.com", "admin")
    _login("csv-admin6@example.com")
    csrf_fail = client.post(
        f"/projects/{project_id}/import/rooms/preview",
        files={"file": ("rooms.csv", io.BytesIO(payload.encode("utf-8")), "text/csv")},
        headers={"X-No-Auto-CSRF": "1"},
    )
    assert csrf_fail.status_code == 403
