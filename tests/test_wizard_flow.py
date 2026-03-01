from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.company_profile import get_or_create_company_profile
from app.models import Project, ProjectWorkItem, User
from app.services.terms_templates import create_versioned_template
from app.scripts.seed_defaults import seed_defaults
from tests.db_utils import clear_database


client = TestClient(app)
settings = get_settings()


def _login() -> None:
    client.post(
        "/login",
        data={"username": settings.admin_email, "password": settings.admin_password, "next": "/projects/"},
        follow_redirects=False,
    )


def _reset_seed_and_project() -> int:
    db = SessionLocal()
    try:
        clear_database(db, exclude_tables={"users"})
        if not db.query(User).filter(User.email == settings.admin_email).first():
            raise AssertionError("admin user missing")
        seed_defaults(db)
        company = get_or_create_company_profile(db)
        company.legal_name = "Wizard Test AB"
        company.org_number = "559999-0000"
        company.address_line1 = "Testgatan 1"
        company.postal_code = "11122"
        company.city = "Stockholm"
        company.email = "test@example.com"
        company.bankgiro = "123-4567"
        db.add(company)
        create_versioned_template(
            db,
            segment="B2C",
            doc_type="OFFER",
            lang="sv",
            title="Standardvillkor Offert",
            body_text="Villkor",
            is_active=True,
        )
        project = Project(name=f"Wizard flow {uuid4().hex[:6]}")
        db.add(project)
        db.commit()
        db.refresh(project)
        return project.id
    finally:
        db.close()


def test_wizard_end_to_end_clean_db_flow():
    _login()
    project_id = _reset_seed_and_project()

    backslash = client.get("/wizard\\object?lang=ru", follow_redirects=False)
    assert backslash.status_code in (307, 308)
    assert backslash.headers["location"].startswith("/wizard/object")

    choose_object = client.post(
        f"/projects/{project_id}/wizard/object",
        data={"lang": "ru", "object_type": "apartment", "object_template": "1br"},
        follow_redirects=False,
    )
    assert choose_object.status_code == 303

    rooms_page = client.get(f"/projects/{project_id}/wizard?step=rooms&lang=ru")
    assert rooms_page.status_code == 200
    assert "Комнаты" in rooms_page.text

    db = SessionLocal()
    try:
        room_id = db.get(Project, project_id).rooms[0].id
    finally:
        db.close()

    room_update = client.post(
        f"/projects/{project_id}/rooms/bulk-update?lang=ru",
        data={
            "room_ids": [str(room_id)],
            f"name_{room_id}": "Гостиная",
            f"floor_area_m2_{room_id}": "20",
            f"height_m_{room_id}": "2.6",
            f"openings_area_m2_{room_id}": "2",
        },
        follow_redirects=False,
    )
    assert room_update.status_code == 303

    works_page = client.get(f"/projects/{project_id}/wizard?step=works&lang=ru")
    assert works_page.status_code == 200
    assert "Каталог пакетов" in works_page.text

    apply_pkg = client.post(
        f"/projects/{project_id}/wizard/packages/apply",
        data={"lang": "ru", "package_code": "PKG_PAINT_WALL_2", "scope_mode": "WHOLE_PROJECT"},
        follow_redirects=False,
    )
    assert apply_pkg.status_code == 303

    db = SessionLocal()
    try:
        items_count = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).count()
    finally:
        db.close()
    assert items_count > 0

    for step in ("pricing", "review", "documents"):
        page = client.get(f"/projects/{project_id}/wizard?step={step}&lang=ru")
        assert page.status_code == 200

    offer_sv = client.get(f"/offers/{project_id}/print?lang=sv")
    offer_pdf = client.get(f"/offers/{project_id}/pdf?lang=sv")
    assert offer_sv.status_code == 200
    assert offer_pdf.status_code == 200
