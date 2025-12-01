from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Client, Project, ProjectWorkItem, Room, WorkType

client = TestClient(app)
settings = get_settings()


def login():
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def create_worktype(db: SessionLocal) -> WorkType:
    worktype = WorkType(
        code=f"WT-{uuid4().hex[:8]}",
        category="test",
        unit="m2",
        name_ru="Тест",
        name_sv="Test",
        description_ru=None,
        description_sv=None,
        hours_per_unit=Decimal("1.0"),
        base_difficulty_factor=Decimal("1.0"),
    )
    db.add(worktype)
    db.commit()
    db.refresh(worktype)
    return worktype


def test_project_edit_and_delete_without_dependencies():
    login()
    db = SessionLocal()
    try:
        project = Project(name="Edit me")
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/edit",
        data={
            "name": "Updated name",
            "client_id": "",
            "address": "Street 1",
            "description": "Desc",
            "status": "in_progress",
            "planned_start_date": "2024-01-01",
            "planned_end_date": "2024-01-10",
            "actual_start_date": "",
            "actual_end_date": "",
            "use_rot": "on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        updated = db.get(Project, project_id)
        assert updated.name == "Updated name"
        assert updated.description == "Desc"
        assert updated.status == "in_progress"
    finally:
        db.close()

    delete_response = client.post(
        f"/projects/{project_id}/delete", follow_redirects=False
    )
    assert delete_response.status_code == 303
    db = SessionLocal()
    try:
        assert db.get(Project, project.id) is None
    finally:
        db.close()


def test_project_delete_blocked_by_dependencies():
    login()
    db = SessionLocal()
    try:
        project = Project(name="With deps")
        worktype = create_worktype(db)
        room = Room(project=project, name="Room")
        item = ProjectWorkItem(
            project=project,
            room=room,
            work_type=worktype,
            quantity=Decimal("1"),
            difficulty_factor=Decimal("1"),
        )
        db.add_all([project, room, item])
        db.commit()
        db.refresh(project)
        project_id = project.id
        room_id = room.id
        item_id = item.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/delete", follow_redirects=True
    )
    assert "Нельзя удалить проект" in response.text

    db = SessionLocal()
    try:
        assert db.get(Project, project_id) is not None
        db.delete(db.get(ProjectWorkItem, item_id))
        db.delete(db.get(Room, room_id))
        db.delete(db.get(Project, project_id))
        db.commit()
    finally:
        db.close()


def test_room_edit_and_delete_blocked():
    login()
    db = SessionLocal()
    try:
        project = Project(name="Rooms project")
        worktype = create_worktype(db)
        room = Room(project=project, name="Kitchen", floor_area_m2=Decimal("12"))
        item = ProjectWorkItem(
            project=project,
            work_type=worktype,
            room=room,
            quantity=Decimal("2"),
            difficulty_factor=Decimal("1"),
        )
        db.add_all([project, room, item])
        db.commit()
        db.refresh(room)
        project_id = project.id
        room_id = room.id
        item_id = item.id
    finally:
        db.close()

    edit_response = client.post(
        f"/projects/{project_id}/rooms/{room_id}/edit",
        data={
            "name": "Kitchen updated",
            "description": "Big room",
            "floor_area_m2": "15",
            "wall_perimeter_m": "20",
            "wall_height_m": "3",
            "wall_area_m2": "60",
            "ceiling_area_m2": "15",
            "baseboard_length_m": "20",
        },
        follow_redirects=False,
    )
    assert edit_response.status_code == 303

    db = SessionLocal()
    try:
        refreshed_room = db.get(Room, room_id)
        assert refreshed_room.name == "Kitchen updated"
        assert refreshed_room.wall_area_m2 == Decimal("60")
    finally:
        db.close()

    delete_response = client.post(
        f"/projects/{project_id}/rooms/{room_id}/delete", follow_redirects=True
    )
    assert "Комната используется в строках сметы" in delete_response.text

    db = SessionLocal()
    try:
        db.delete(db.get(ProjectWorkItem, item_id))
        db.delete(db.get(Room, room_id))
        db.delete(db.get(Project, project_id))
        db.commit()
    finally:
        db.close()


def test_client_edit_and_delete_rules():
    login()
    db = SessionLocal()
    try:
        client_entity = Client(name="Client A")
        project = Project(name="Client project", client=client_entity)
        db.add_all([client_entity, project])
        db.commit()
        db.refresh(client_entity)
        client_id = client_entity.id
        project_id = project.id
    finally:
        db.close()

    edit_response = client.post(
        f"/clients/{client_id}/edit",
        data={
            "name": "Client B",
            "contact_person": "John",
            "phone": "123",
            "email": "test@example.com",
            "address": "Street",
            "comment": "Updated",
        },
        follow_redirects=False,
    )
    assert edit_response.status_code == 303

    db = SessionLocal()
    try:
        updated_client = db.get(Client, client_id)
        assert updated_client.name == "Client B"
    finally:
        db.close()

    blocked_delete = client.post(
        f"/clients/{client_id}/delete", follow_redirects=True
    )
    assert "Нельзя удалить клиента" in blocked_delete.text

    db = SessionLocal()
    try:
        db.delete(db.get(Project, project_id))
        db.commit()
    finally:
        db.close()

    allowed_delete = client.post(
        f"/clients/{client_id}/delete", follow_redirects=False
    )
    assert allowed_delete.status_code == 303
    db = SessionLocal()
    try:
        assert db.get(Client, client_id) is None
    finally:
        db.close()
