import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.client import Client
from app.models.project import Project

client = TestClient(app)


def _login() -> None:
    settings = get_settings()
    client.post(
        "/login",
        data={"username": settings.admin_email, "password": settings.admin_password, "next": "/projects/"},
        follow_redirects=False,
    )


def _project_id() -> int:
    db = SessionLocal()
    try:
        c = Client(name=f"Tabs Client {uuid.uuid4()}")
        db.add(c)
        db.flush()
        p = Project(name=f"Tabs Project {uuid.uuid4()}", client_id=c.id, status="draft")
        db.add(p)
        db.commit()
        return p.id
    finally:
        db.close()


def test_project_tabs_layout_and_links():
    _login()
    project_id = _project_id()

    overview = client.get(f"/projects/{project_id}")
    assert overview.status_code == 200
    assert f"/projects/{project_id}?tab=overview" in overview.text
    assert f"/projects/{project_id}/estimator" in overview.text
    assert f"/projects/{project_id}/materials-plan" in overview.text
    assert f"/projects/{project_id}/shopping-list" in overview.text

    assert client.get(f"/projects/{project_id}/estimator").status_code == 200
    assert client.get(f"/projects/{project_id}/materials-plan").status_code == 200
    assert client.get(f"/projects/{project_id}/shopping-list").status_code == 200
