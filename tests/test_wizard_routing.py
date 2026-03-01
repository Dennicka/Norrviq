from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.project import Project

client = TestClient(app)
settings = get_settings()


def _login() -> None:
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def _seed_project() -> int:
    db = SessionLocal()
    try:
        project = Project(name=f"Wizard {uuid4().hex[:6]}")
        db.add(project)
        db.commit()
        return project.id
    finally:
        db.close()


def test_wizard_routing_steps_and_invalid_redirect():
    _login()
    project_id = _seed_project()

    rooms = client.get(f"/projects/{project_id}/wizard?step=object&lang=ru")
    assert rooms.status_code == 200
    assert "Мастер сметы" in rooms.text

    pricing = client.get(f"/projects/{project_id}/wizard?step=pricing&lang=en")
    assert pricing.status_code == 200
    assert "Pricing" in pricing.text

    invalid = client.get(f"/projects/{project_id}/wizard?step=bad&lang=ru", follow_redirects=False)
    assert invalid.status_code == 303
    assert f"/projects/{project_id}/wizard?step=object&lang=ru" in invalid.headers["location"]
