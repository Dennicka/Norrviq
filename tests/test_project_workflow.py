from decimal import Decimal
import re

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import CompanyProfile, Invoice, Project, ProjectPricing, ProjectWorkItem, Room, WorkType

client = TestClient(app)
settings = get_settings()
CSRF_META_RE = re.compile(r'<meta\s+name="csrf-token"\s+content="([^"]+)"')


def _csrf(html: str) -> str:
    return CSRF_META_RE.search(html).group(1)


def _login():
    page = client.get("/login")
    token = _csrf(page.text)
    client.post(
        "/login",
        data={"username": settings.admin_email, "password": settings.admin_password, "csrf_token": token},
        headers={"X-CSRF-Token": token},
    )


def _seed_project(ready: bool = False) -> int:
    db = SessionLocal()
    try:
        project = Project(name="WF web")
        db.add(project)
        db.flush()
        if ready:
            profile = db.query(CompanyProfile).first()
            if profile:
                profile.org_number = "556677-8899"
                profile.vat_number = "SE556677889901"
            room = Room(project_id=project.id, name="A", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("12"), wall_height_m=Decimal("2.4"))
            wt = WorkType(code=f"WFW-{project.id}", unit="m2", name_ru="Покраска", name_sv="Paint", hours_per_unit=Decimal("1"), base_difficulty_factor=Decimal("1"))
            db.add_all([room, wt])
            db.flush()
            db.add(ProjectWorkItem(project_id=project.id, room_id=room.id, work_type_id=wt.id, quantity=Decimal("4"), calculated_hours=Decimal("4"), difficulty_factor=Decimal("1")))
            db.add(ProjectPricing(project_id=project.id, mode="HOURLY", hourly_rate_override=Decimal("400")))
        db.commit()
        return project.id
    finally:
        db.close()


def test_workflow_page_renders():
    _login()
    project_id = _seed_project()
    response = client.get(f"/projects/{project_id}/workflow")
    assert response.status_code == 200
    assert "Шаги workflow" in response.text


def test_create_offer_draft_blocked_when_not_ready():
    _login()
    project_id = _seed_project(ready=False)
    page = client.get(f"/projects/{project_id}/workflow")
    token = _csrf(page.text)
    response = client.post(
        f"/projects/{project_id}/workflow/create-offer-draft",
        data={"csrf_token": token},
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/workflow")


def test_create_offer_draft_success_when_ready():
    _login()
    project_id = _seed_project(ready=True)
    page = client.get(f"/projects/{project_id}/workflow")
    token = _csrf(page.text)
    response = client.post(
        f"/projects/{project_id}/workflow/create-offer-draft",
        data={"csrf_token": token},
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        assert project.offer_status == "draft"
        assert project.offer_commercial_snapshot
    finally:
        db.close()


def test_create_invoice_draft_blocked_before_offer_gate():
    _login()
    project_id = _seed_project(ready=False)
    page = client.get(f"/projects/{project_id}/workflow")
    token = _csrf(page.text)
    response = client.post(
        f"/projects/{project_id}/workflow/create-invoice-draft",
        data={"csrf_token": token},
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/workflow")


def test_create_invoice_draft_idempotent():
    _login()
    project_id = _seed_project(ready=True)
    page = client.get(f"/projects/{project_id}/workflow")
    token = _csrf(page.text)

    r1 = client.post(f"/projects/{project_id}/workflow/create-invoice-draft", data={"csrf_token": token}, headers={"X-CSRF-Token": token}, follow_redirects=False)
    r2 = client.post(f"/projects/{project_id}/workflow/create-invoice-draft", data={"csrf_token": token}, headers={"X-CSRF-Token": token}, follow_redirects=False)

    assert r1.status_code == 303 and r2.status_code == 303
    db = SessionLocal()
    try:
        drafts = db.query(Invoice).filter(Invoice.project_id == project_id, Invoice.status == "draft").all()
        assert len(drafts) == 1
    finally:
        db.close()


def test_workflow_recalculate_redirects_back():
    _login()
    project_id = _seed_project(ready=True)
    page = client.get(f"/projects/{project_id}/workflow")
    token = _csrf(page.text)
    response = client.post(
        f"/projects/{project_id}/workflow/recalculate",
        data={"csrf_token": token},
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/workflow")


def test_workflow_uses_localized_ru_label_smoke():
    _login()
    project_id = _seed_project()
    response = client.get(f"/projects/{project_id}/workflow?lang=ru")
    assert "Статус workflow" in response.text
