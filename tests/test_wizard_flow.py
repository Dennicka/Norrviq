from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.project import Project
from app.models.room import Room
from app.models.project import ProjectWorkItem
from app.scripts.seed_defaults import seed_defaults

client = TestClient(app)
settings = get_settings()


def _login() -> None:
    client.post("/login", data={"username": settings.admin_email, "password": settings.admin_password})


def test_wizard_flow_fresh_seed_ru_and_pdf_endpoints():
    seed_defaults()
    _login()

    db = SessionLocal()
    try:
        project = Project(name=f"Wizard Flow {uuid4().hex[:6]}")
        db.add(project)
        db.commit()
        db.refresh(project)
        room = Room(project_id=project.id, name="Комната 1", floor_area_m2=20, wall_height_m=2.6)
        db.add(room)
        db.commit()
        project_id = project.id
    finally:
        db.close()

    assert client.get("/wizard/object?lang=ru", follow_redirects=False).status_code in (302, 303)

    object_page = client.get(f"/projects/{project_id}/wizard?step=object&lang=ru")
    assert object_page.status_code == 200
    assert "Дом" in object_page.text
    assert "Квартира" in object_page.text

    apply_response = client.post(
        f"/projects/{project_id}/wizard/packages/apply",
        data={"package_code": "PKG_PAINT_WALL_2", "scope_mode": "WHOLE_PROJECT"},
        follow_redirects=False,
    )
    assert apply_response.status_code == 303

    db = SessionLocal()
    try:
        assert db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).count() > 0
    finally:
        db.close()

    offer_page = client.get(f"/projects/{project_id}/offer?lang=sv")
    assert offer_page.status_code == 200
    offer_pdf = client.get(f"/offers/{project_id}/pdf?lang=sv")
    assert offer_pdf.status_code == 200
