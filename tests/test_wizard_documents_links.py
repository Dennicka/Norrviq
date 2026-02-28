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
        project = Project(name=f"Wizard docs {uuid4().hex[:6]}")
        db.add(project)
        db.commit()
        return project.id
    finally:
        db.close()


def test_wizard_documents_step_contains_offer_links_with_lang():
    _login()
    project_id = _seed_project()

    response = client.get(f"/projects/{project_id}/wizard?step=documents&lang=en")
    assert response.status_code == 200
    assert f"/offers/{project_id}/print?lang=en" in response.text
    assert f"/offers/{project_id}/pdf?lang=en" in response.text
