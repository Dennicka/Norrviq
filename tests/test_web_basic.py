from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Project
from app.models.room import Room

client = TestClient(app)
settings = get_settings()


def login():
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def test_clients_page():
    login()
    response = client.get("/clients/")
    assert response.status_code == 200


def test_worktypes_page():
    login()
    response = client.get("/worktypes/")
    assert response.status_code == 200


def test_projects_page():
    login()
    response = client.get("/projects/")
    assert response.status_code == 200


def test_project_detail_has_rooms_section():
    login()
    db = SessionLocal()
    try:
        project = Project(name="Rooms project")
        db.add(project)
        db.commit()
        db.refresh(project)
    finally:
        db.close()

    detail = client.get(f"/projects/{project.id}")
    assert detail.status_code == 200
    assert "rooms.section_title" not in detail.text  # ensure translation called
    assert "Комнаты и зоны" in detail.text or "Rum och zoner" in detail.text


def test_project_detail_shows_geometry_summary():
    login()
    db = SessionLocal()
    try:
        project = Project(name="Geometry project")
        db.add(project)
        db.flush()
        room = Room(
            project_id=project.id,
            name="Room 1",
            length_m=5,
            width_m=4,
            wall_height_m=2.5,
            openings_area_m2=3,
        )
        db.add(room)
        db.commit()
        db.refresh(project)
    finally:
        db.close()

    detail = client.get(f"/projects/{project.id}")
    assert detail.status_code == 200
    assert "Геометрия проекта" in detail.text
    assert "42.00" in detail.text
    assert "45.00" in detail.text
