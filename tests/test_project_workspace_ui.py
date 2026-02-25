import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.client import Client
from app.models.company_profile import get_or_create_company_profile
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.project import Project
from app.models.user import User
from app.security import hash_password

client = TestClient(app)


def _login_admin() -> None:
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == "workspace-admin@example.com").first():
            db.add(User(email="workspace-admin@example.com", password_hash=hash_password("Password#123"), role="admin"))
            db.commit()
    finally:
        db.close()
    client.post("/login", data={"username": "workspace-admin@example.com", "password": "Password#123"})


def _project_id(with_invoice: bool = False) -> tuple[int, int | None]:
    db = SessionLocal()
    try:
        c = Client(name=f"Workspace Client {uuid.uuid4()}")
        db.add(c)
        db.flush()
        p = Project(name=f"Workspace Project {uuid.uuid4()}", client_id=c.id, status="draft")
        db.add(p)
        db.flush()
        invoice_id = None
        if with_invoice:
            inv = Invoice(
                project_id=p.id,
                status="draft",
                issue_date=date.today(),
                work_sum_without_moms=Decimal("100"),
                moms_amount=Decimal("25"),
                rot_amount=Decimal("0"),
                client_pays_total=Decimal("125"),
                subtotal_ex_vat=Decimal("100"),
                vat_total=Decimal("25"),
                total_inc_vat=Decimal("125"),
            )
            db.add(inv)
            db.flush()
            db.add(
                InvoiceLine(
                    invoice_id=inv.id,
                    position=1,
                    kind="OTHER",
                    description="Line",
                    unit="h",
                    quantity=Decimal("2"),
                    unit_price_ex_vat=Decimal("50"),
                    vat_rate_pct=Decimal("25"),
                    line_total_ex_vat=Decimal("100"),
                    source_type="MANUAL",
                )
            )
            invoice_id = inv.id
        db.commit()
        return p.id, invoice_id
    finally:
        db.close()


def test_workspace_tabs_render_and_tab_query_works():
    _login_admin()
    project_id, _ = _project_id()
    response = client.get(f"/projects/{project_id}?tab=pricing")
    assert response.status_code == 200
    assert "projects.workspace.tab.pricing" not in response.text
    assert 'class="active">Политика цен<' in response.text
    assert 'data-tab="pricing"' in response.text


def test_workspace_recalculate_redirect_preserves_tab():
    _login_admin()
    project_id, _ = _project_id()
    response = client.post(f"/projects/{project_id}/recalculate?tab=scope", data={}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/projects/{project_id}?tab=scope")


def test_workspace_summary_and_help_icons_present():
    _login_admin()
    project_id, _ = _project_id()
    response = client.get(f"/projects/{project_id}?tab=overview")
    assert response.status_code == 200
    assert "Резюме проекта" in response.text
    assert "projects.workspace.summary.total_ex" not in response.text
    assert "help-popover" in response.text


def test_documents_section_renders_preview_and_controls():
    _login_admin()
    project_id, invoice_id = _project_id(with_invoice=True)

    response = client.get(f"/projects/{project_id}?tab=documents&doc_type=invoice")

    assert response.status_code == 200
    assert "Документы проекта" in response.text
    assert 'name="doc_type"' in response.text
    assert 'name="document_lang"' in response.text
    assert 'class="documents-preview-frame"' in response.text
    assert f"/projects/{project_id}/invoices/{invoice_id}" in response.text


def test_documents_preferences_persist_offer_and_invoice_language():
    _login_admin()
    project_id, invoice_id = _project_id(with_invoice=True)

    response_offer = client.post(
        f"/projects/{project_id}/documents/preferences",
        data={"doc_type": "offer", "document_lang": "en"},
        follow_redirects=False,
    )
    assert response_offer.status_code == 303

    response_invoice = client.post(
        f"/projects/{project_id}/documents/preferences",
        data={"doc_type": "invoice", "invoice_id": invoice_id, "document_lang": "ru"},
        follow_redirects=False,
    )
    assert response_invoice.status_code == 303

    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        invoice = db.get(Invoice, invoice_id)
        assert project.offer_document_lang == "en"
        assert invoice.document_lang == "ru"
    finally:
        db.close()


def test_documents_section_shows_company_profile_warning_when_required_fields_missing():
    _login_admin()
    project_id, _ = _project_id(with_invoice=False)
    db = SessionLocal()
    try:
        profile = get_or_create_company_profile(db)
        profile.org_number = ""
        profile.address_line1 = ""
        profile.email = ""
        profile.bankgiro = ""
        profile.plusgiro = ""
        profile.iban = ""
        db.add(profile)
        db.commit()
    finally:
        db.close()

    response = client.get(f"/projects/{project_id}?tab=documents")

    assert response.status_code == 200
    assert "Заполните реквизиты компании" in response.text
    assert "Открыть Компания" in response.text
