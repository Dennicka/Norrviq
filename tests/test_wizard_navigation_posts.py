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
        project = Project(name=f"Wizard nav {uuid4().hex[:6]}")
        db.add(project)
        db.commit()
        return project.id
    finally:
        db.close()


def test_wizard_next_and_back_preserve_lang():
    _login()
    project_id = _seed_project()

    next_response = client.post(
        f"/projects/{project_id}/wizard/next",
        data={"step": "rooms", "lang": "en"},
        follow_redirects=False,
    )
    assert next_response.status_code == 303
    assert "step=works" in next_response.headers["location"]
    assert "lang=en" in next_response.headers["location"]

    back_response = client.post(
        f"/projects/{project_id}/wizard/back",
        data={"step": "works", "lang": "en"},
        follow_redirects=False,
    )
    assert back_response.status_code == 303
    assert "step=rooms" in back_response.headers["location"]
    assert "lang=en" in back_response.headers["location"]
