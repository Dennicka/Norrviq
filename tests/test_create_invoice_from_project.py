from decimal import Decimal
import re

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import CostCategory, Invoice, Project, ProjectCostItem, ProjectPricing, ProjectWorkItem, Room, User, WorkType
from app.security import hash_password

client = TestClient(app)
settings = get_settings()
CSRF_META_RE = re.compile(r'<meta\s+name="csrf-token"\s+content="([^"]+)"')


def _csrf(html: str) -> str:
    return CSRF_META_RE.search(html).group(1)


def _login(email=None, password=None):
    login_page = client.get("/login")
    token = _csrf(login_page.text)
    client.post(
        "/login",
        data={"username": email or settings.admin_email, "password": password or settings.admin_password, "csrf_token": token},
        headers={"X-CSRF-Token": token},
    )


def _create_project_with_data() -> int:
    db = SessionLocal()
    try:
        project = Project(name="InvoiceFromProject")
        db.add(project)
        db.flush()

        room = Room(project_id=project.id, name="Hall")
        wt = WorkType(code=f"CIP-{project.id}", unit="m2", name_ru="Покраска", name_sv="Paint", hours_per_unit=Decimal("1.0"), base_difficulty_factor=Decimal("1.0"))
        db.add_all([room, wt])
        db.flush()

        db.add(ProjectPricing(project_id=project.id, mode="HOURLY", hourly_rate_override=Decimal("400")))
        db.add(ProjectWorkItem(project_id=project.id, room_id=room.id, work_type_id=wt.id, quantity=Decimal("5"), calculated_hours=Decimal("5"), calculated_cost_without_moms=Decimal("2000"), difficulty_factor=Decimal("1.0")))

        category = db.query(CostCategory).first()
        if category is None:
            category = CostCategory(code=f"MAT-{project.id}", name_ru="Материалы", name_sv="Materials")
            db.add(category)
            db.flush()

        db.add(ProjectCostItem(project_id=project.id, cost_category_id=category.id, title="Primer", amount=Decimal("150.00"), moms_amount=Decimal("37.50"), is_material=True))
        db.commit()
        return project.id
    finally:
        db.close()


def test_create_invoice_from_project_creates_draft_and_lines():
    _login()
    project_id = _create_project_with_data()
    page = client.get(f"/projects/{project_id}")
    token = _csrf(page.text)

    response = client.post(
        f"/projects/{project_id}/invoices/create-from-project",
        data={"include_labor": "true", "merge_strategy": "REPLACE_ALL", "csrf_token": token},
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    db = SessionLocal()
    try:
        invoice = db.query(Invoice).filter(Invoice.project_id == project_id).first()
        assert invoice is not None
        assert invoice.status == "draft"
        assert len(invoice.lines) >= 1
        assert invoice.total_inc_vat >= 0
    finally:
        db.close()


def test_create_invoice_from_project_idempotent_returns_same_draft():
    _login()
    project_id = _create_project_with_data()
    page = client.get(f"/projects/{project_id}")
    token = _csrf(page.text)

    first = client.post(
        f"/projects/{project_id}/invoices/create-from-project",
        data={"include_labor": "true", "merge_strategy": "REPLACE_ALL", "csrf_token": token},
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    second = client.post(
        f"/projects/{project_id}/invoices/create-from-project",
        data={"include_labor": "true", "merge_strategy": "REPLACE_ALL", "csrf_token": token},
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )

    assert first.status_code == 303
    assert second.status_code == 303
    assert first.headers["location"] == second.headers["location"]

    db = SessionLocal()
    try:
        drafts = db.query(Invoice).filter(Invoice.project_id == project_id, Invoice.status == "draft").all()
        assert len(drafts) == 1
    finally:
        db.close()


def test_create_invoice_from_project_requires_role_and_csrf():
    _login()
    project_id = _create_project_with_data()

    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == "viewer-cip@example.com").first():
            db.add(User(email="viewer-cip@example.com", password_hash=hash_password("pw"), role="viewer"))
            db.commit()
    finally:
        db.close()

    _login("viewer-cip@example.com", "pw")
    page = client.get(f"/projects/{project_id}")
    token = _csrf(page.text)
    forbidden = client.post(
        f"/projects/{project_id}/invoices/create-from-project",
        data={"csrf_token": token},
        headers={"X-CSRF-Token": token},
    )
    assert forbidden.status_code == 403

    _login()
    no_csrf = client.post(
        f"/projects/{project_id}/invoices/create-from-project",
        data={},
        headers={"X-No-Auto-CSRF": "1"},
    )
    assert no_csrf.status_code == 403


def test_create_invoice_from_project_respects_include_materials_flag():
    _login()
    project_id = _create_project_with_data()
    page = client.get(f"/projects/{project_id}")
    token = _csrf(page.text)

    client.post(
        f"/projects/{project_id}/invoices/create-from-project",
        data={"include_labor": "true", "include_materials": "false", "merge_strategy": "REPLACE_ALL", "csrf_token": token},
        headers={"X-CSRF-Token": token},
    )

    db = SessionLocal()
    try:
        invoice = db.query(Invoice).filter(Invoice.project_id == project_id).first()
        without_materials = len([line for line in invoice.lines if line.kind == "MATERIAL"])
    finally:
        db.close()

    client.post(
        f"/projects/{project_id}/invoices/create-from-project",
        data={"include_labor": "true", "include_materials": "true", "merge_strategy": "REPLACE_ALL", "csrf_token": token},
        headers={"X-CSRF-Token": token},
    )

    db = SessionLocal()
    try:
        invoice = db.query(Invoice).filter(Invoice.project_id == project_id).first()
        with_materials = len([line for line in invoice.lines if line.kind == "MATERIAL"])
    finally:
        db.close()

    assert without_materials == 0
    assert with_materials > 0


def test_create_invoice_from_project_redirects_to_invoice_page():
    _login()
    project_id = _create_project_with_data()
    page = client.get(f"/projects/{project_id}")
    token = _csrf(page.text)

    response = client.post(
        f"/projects/{project_id}/invoices/create-from-project",
        data={"include_labor": "true", "merge_strategy": "REPLACE_ALL", "csrf_token": token},
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/projects/{project_id}/invoices/")
