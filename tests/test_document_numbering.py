from concurrent.futures import ThreadPoolExecutor
from datetime import date

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.company_profile import get_or_create_company_profile
from app.models.invoice import Invoice
from app.models.project import Project
from app.models.user import User
from app.security import hash_password
from app.services.document_numbering import finalize_invoice, format_document_number

client = TestClient(app)
settings = get_settings()


def _login(username: str, password: str):
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


def _create_project_with_invoice() -> tuple[int, int]:
    db = SessionLocal()
    try:
        project = Project(name="Numbering project")
        db.add(project)
        db.commit()
        db.refresh(project)
        invoice = Invoice(
            project_id=project.id,
            invoice_number=None,
            issue_date=date.today(),
            status="draft",
            work_sum_without_moms=0,
            moms_amount=0,
            rot_amount=0,
            client_pays_total=0,
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        return project.id, invoice.id
    finally:
        db.close()


def test_format_number_padding():
    assert format_document_number("OF-", 2026, 1, 4) == "OF-2026-0001"
    assert format_document_number("TR-", 2026, 12, 6) == "TR-2026-000012"


def test_offer_finalize_assigns_unique_number_and_idempotent():
    _login(settings.admin_email, settings.admin_password)
    db = SessionLocal()
    try:
        project = Project(name="Offer finalize")
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()

    first = client.post(f"/offers/{project_id}/finalize", follow_redirects=False)
    second = client.post(f"/offers/{project_id}/finalize", follow_redirects=False)
    assert first.status_code == 303
    assert second.status_code == 303

    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        assert project.offer_status == "issued"
        assert project.offer_number
        first_number = project.offer_number
    finally:
        db.close()

    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        assert project.offer_number == first_number
    finally:
        db.close()


def test_invoice_finalize_assigns_unique_number():
    _login(settings.admin_email, settings.admin_password)
    _, invoice_id = _create_project_with_invoice()

    response = client.post(f"/invoices/{invoice_id}/finalize", follow_redirects=False)
    assert response.status_code == 303

    db = SessionLocal()
    try:
        invoice = db.get(Invoice, invoice_id)
        assert invoice.status == "issued"
        assert invoice.invoice_number is not None
    finally:
        db.close()


def test_finalize_requires_role():
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == "viewer-finalize@example.com").first():
            db.add(User(email="viewer-finalize@example.com", password_hash=hash_password("pw"), role="viewer"))
            db.commit()
    finally:
        db.close()

    _, invoice_id = _create_project_with_invoice()
    client.get("/logout")
    _login("viewer-finalize@example.com", "pw")
    response = client.post(f"/invoices/{invoice_id}/finalize", follow_redirects=False)
    assert response.status_code == 403


def test_concurrent_invoice_finalize_unique_numbers():
    ids = []
    for _ in range(2):
        _, invoice_id = _create_project_with_invoice()
        ids.append(invoice_id)

    def _finalize(invoice_id: int):
        db = SessionLocal()
        try:
            profile = get_or_create_company_profile(db)
            finalize_invoice(db, invoice_id=invoice_id, user_id="thread", profile=profile)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as ex:
        list(ex.map(_finalize, ids))

    db = SessionLocal()
    try:
        rows = [db.get(Invoice, invoice_id) for invoice_id in ids]
        numbers = [row.invoice_number for row in rows]
        assert len(set(numbers)) == 2
        assert all(row.status == "issued" for row in rows)
    finally:
        db.close()


def test_number_exists_only_when_issued():
    _, invoice_id = _create_project_with_invoice()

    db = SessionLocal()
    try:
        invoice = db.get(Invoice, invoice_id)
        assert invoice.status == "draft"
        assert invoice.invoice_number is None
    finally:
        db.close()
