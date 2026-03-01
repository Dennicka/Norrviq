from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.project import Project
from app.models.room import Room

client = TestClient(app)
settings = get_settings()


def _login() -> None:
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def _seed_project() -> int:
    db = SessionLocal()
    try:
        project = Project(name=f"Wizard v2 {uuid4().hex[:6]}")
        db.add(project)
        db.commit()
        return project.id
    finally:
        db.close()


def test_wizard_defaults_to_object_step():
    _login()
    project_id = _seed_project()
    response = client.get(f"/projects/{project_id}/wizard", follow_redirects=False)
    assert response.status_code == 303
    assert "step=object" in response.headers["location"]


def test_object_step_renders_project_type_cards():
    _login()
    project_id = _seed_project()
    response = client.get(f"/projects/{project_id}/wizard?step=object")
    assert response.status_code == 200
    for expected in ("House", "Apartment", "Office", "Commercial"):
        assert expected in response.text


def test_applying_template_creates_rooms_and_redirects_to_rooms_step():
    _login()
    project_id = _seed_project()
    response = client.post(
        f"/projects/{project_id}/wizard/object",
        data={"object_type": "apartment", "object_template": "2br", "lang": "sv"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "step=rooms" in response.headers["location"]

    db = SessionLocal()
    try:
        rooms = db.query(Room).filter(Room.project_id == project_id).all()
        assert len(rooms) >= 5
    finally:
        db.close()


def test_review_step_contains_offer_print_and_pdf_links():
    _login()
    project_id = _seed_project()
    response = client.get(f"/projects/{project_id}/wizard?step=review&lang=sv")
    assert response.status_code == 200
    assert f"/offers/{project_id}/print?lang=sv" in response.text
    assert f"/offers/{project_id}/pdf?lang=sv" in response.text
