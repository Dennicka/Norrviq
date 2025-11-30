from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Project

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
