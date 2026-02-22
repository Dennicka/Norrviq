from datetime import date
from decimal import Decimal
from io import BytesIO
import uuid
import importlib.util

from fastapi.testclient import TestClient
import pytest

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.client import Client
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.rot_case import RotCase
from app.models.project import Project, ProjectWorkItem
from app.models.worktype import WorkType
from tests.utils.pdf_text import norm_pdf_text

client = TestClient(app)
settings = get_settings()

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("weasyprint") is None or importlib.util.find_spec("pypdf") is None,
    reason="PDF dependencies are not installed in this environment",
)


def login() -> None:
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def _create_offer_project(*, issued: bool) -> int:
    db = SessionLocal()
    try:
        c = Client(name=f"Client-{uuid.uuid4()}", address="Addr")
        db.add(c)
        db.flush()
        wt = WorkType(
            code=f"WT-PDF-{uuid.uuid4()}",
            category="paint",
            unit="h",
            name_ru="Покраска",
            description_ru="Покраска",
            name_sv="Målning",
            description_sv="Målning",
            hours_per_unit=Decimal("1.0"),
            base_difficulty_factor=Decimal("1.0"),
        )
        db.add(wt)
        db.flush()
        project = Project(
            name="PDF Offer",
            client_id=c.id,
            offer_status="issued" if issued else "draft",
            offer_number="OF-2026-0001" if issued else None,
            offer_terms_snapshot_title="Offer Terms",
            offer_terms_snapshot_body="Snapshot Terms Body",
        )
        db.add(project)
        db.flush()
        db.add(
            ProjectWorkItem(
                project_id=project.id,
                work_type_id=wt.id,
                quantity=Decimal("2"),
                difficulty_factor=Decimal("1.0"),
            )
        )
        db.commit()
        return project.id
    finally:
        db.close()


def _create_invoice(*, issued: bool) -> int:
    db = SessionLocal()
    try:
        c = Client(name=f"Client-{uuid.uuid4()}", address="Addr")
        db.add(c)
        db.flush()
        project = Project(name="PDF Invoice", client_id=c.id)
        db.add(project)
        db.flush()
        invoice = Invoice(
            project_id=project.id,
            status="issued" if issued else "draft",
            invoice_number="TR-2026-0001" if issued else None,
            issue_date=date.today(),
            work_sum_without_moms=Decimal("100"),
            moms_amount=Decimal("25"),
            rot_amount=Decimal("0"),
            client_pays_total=Decimal("125"),
            subtotal_ex_vat=Decimal("100"),
            vat_total=Decimal("25"),
            total_inc_vat=Decimal("125"),
            invoice_terms_snapshot_title="Invoice Terms",
            invoice_terms_snapshot_body="Invoice Snapshot Terms",
        )
        db.add(invoice)
        db.flush()
        db.add(
            InvoiceLine(
                invoice_id=invoice.id,
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
        db.commit()
        return invoice.id
    finally:
        db.close()


def _extract_text(content: bytes) -> str:
    import pytest

    pdf_reader = pytest.importorskip("pypdf").PdfReader
    reader = pdf_reader(BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_offer_pdf_endpoint_returns_pdf():
    project_id = _create_offer_project(issued=False)
    login()

    response = client.get(f"/offers/{project_id}/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_invoice_pdf_endpoint_returns_pdf():
    invoice_id = _create_invoice(issued=False)
    login()

    response = client.get(f"/invoices/{invoice_id}/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_invoice_pdf_contains_rot_text():
    invoice_id = _create_invoice(issued=False)
    db = SessionLocal()
    try:
        db.add(RotCase(invoice_id=invoice_id, is_enabled=True, rot_pct=Decimal("30"), rot_amount=Decimal("30"), eligible_labor_ex_vat=Decimal("100")))
        invoice = db.get(Invoice, invoice_id)
        invoice.labour_ex_vat = Decimal("100")
        invoice.material_ex_vat = Decimal("0")
        invoice.vat_total = Decimal("25")
        invoice.rot_amount = Decimal("30")
        invoice.client_pays_total = Decimal("95")
        db.commit()
    finally:
        db.close()
    login()

    response = client.get(f"/invoices/{invoice_id}/pdf")

    assert response.status_code == 200
    text = _extract_text(response.content)
    assert "ROT-avdrag" in text


def test_pdf_requires_auth():
    project_id = _create_offer_project(issued=False)
    client.cookies.clear()

    response = client.get(f"/offers/{project_id}/pdf", follow_redirects=False)

    assert response.status_code in (302, 401)


def test_issued_pdf_uses_snapshot_terms():
    project_id = _create_offer_project(issued=True)
    login()

    response = client.get(f"/offers/{project_id}/pdf")

    assert response.status_code == 200
    text = _extract_text(response.content)
    assert "OF-2026-0001" in text
    assert norm_pdf_text("Snapshot Terms Body") in norm_pdf_text(text)
