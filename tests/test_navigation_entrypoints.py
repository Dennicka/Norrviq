from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.project import Project

client = TestClient(app)
settings = get_settings()


def _login() -> None:
    client.post(
        "/login",
        data={"username": settings.admin_email, "password": settings.admin_password, "next": "/projects/"},
        follow_redirects=False,
    )


def _seed_project() -> int:
    db = SessionLocal()
    try:
        project = Project(name=f"Navigation test {uuid4().hex[:6]}")
        db.add(project)
        db.commit()
        return project.id
    finally:
        db.close()


def test_estimator_invoice_link_is_valid():
    _login()
    project_id = _seed_project()

    response = client.get(f"/projects/{project_id}/estimator")

    assert response.status_code == 200
    assert f"/projects/{project_id}/invoices/new" not in response.text
    assert f"/projects/{project_id}/invoices/create" in response.text


def test_project_detail_has_rooms_tab_link():
    _login()
    project_id = _seed_project()

    response = client.get(f"/projects/{project_id}?tab=overview")

    assert response.status_code == 200
    assert f"/projects/{project_id}?tab=rooms" in response.text


def test_project_pages_have_wizard_link():
    _login()
    project_id = _seed_project()

    detail = client.get(f"/projects/{project_id}")
    estimator = client.get(f"/projects/{project_id}/estimator")

    assert detail.status_code == 200
    assert estimator.status_code == 200
    assert f"/projects/{project_id}/wizard?step=object" in detail.text
    assert f"/projects/{project_id}/wizard?step=object" in estimator.text
