from datetime import date
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.client import Client
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.project import Project

client = TestClient(app)
settings = get_settings()


def login() -> None:
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def _create_invoice() -> tuple[int, int]:
    db = SessionLocal()
    try:
        c = Client(name=f"Client-{uuid.uuid4()}", address="Addr")
        db.add(c)
        db.flush()
        project = Project(name="Invoice Fallback", client_id=c.id)
        db.add(project)
        db.flush()
        invoice = Invoice(
            project_id=project.id,
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
        return project.id, invoice.id
    finally:
        db.close()


def test_invoice_preview_opens_with_pdf_fallback(monkeypatch):
    project_id, invoice_id = _create_invoice()
    login()
    monkeypatch.setattr("app.services.pdf_renderer.is_weasyprint_available", lambda: False)

    response = client.get(f"/projects/{project_id}/invoices/{invoice_id}?lang=ru")

    assert response.status_code == 200
    assert "PDF" in response.text
    assert "резервный режим" in response.text or "fallback mode" in response.text or "reservläge" in response.text


def test_invoice_pdf_redirects_to_print_view_when_weasyprint_missing(monkeypatch):
    _, invoice_id = _create_invoice()
    login()
    monkeypatch.setattr("app.services.pdf_renderer.is_weasyprint_available", lambda: False)

    response = client.get(f"/invoices/{invoice_id}/pdf", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/invoices/{invoice_id}/print?lang=sv"

    print_response = client.get(response.headers["location"])
    assert print_response.status_code == 200
    assert "text/html" in print_response.headers["content-type"]
    assert "reservläge" in print_response.text
    assert "Dokumentspråk" in print_response.text
    assert "top-nav" not in print_response.text
    assert "offer-toolbar" not in print_response.text


def test_invoice_pdf_keeps_legacy_html_render_contract(monkeypatch):
    _, invoice_id = _create_invoice()
    login()
    captured = {}

    def _fake_render(*, html, base_url, stylesheet_path):
        captured["html"] = html
        return b"%PDF-1.4 fake"

    monkeypatch.setattr("app.services.pdf_renderer.is_weasyprint_available", lambda: True)
    monkeypatch.setattr("app.routers.web_documents.render_pdf_from_html", _fake_render)

    response = client.get(f"/invoices/{invoice_id}/pdf")

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert "html" in captured
    assert "invoice-header" in captured["html"]



def test_invoice_document_renders_ru_labels():
    project_id, invoice_id = _create_invoice()
    login()
    db = SessionLocal()
    try:
        invoice = db.get(Invoice, invoice_id)
        invoice.document_lang = "ru"
        db.add(invoice)
        db.commit()
    finally:
        db.close()

    response = client.get(f"/projects/{project_id}/invoices/{invoice_id}?lang=sv")
    assert response.status_code == 200
    assert "Язык документа" in response.text
    assert "Счёт" in response.text


def test_invoice_document_renders_sv_labels():
    project_id, invoice_id = _create_invoice()
    login()
    db = SessionLocal()
    try:
        invoice = db.get(Invoice, invoice_id)
        invoice.document_lang = "sv"
        db.add(invoice)
        db.commit()
    finally:
        db.close()

    response = client.get(f"/projects/{project_id}/invoices/{invoice_id}?lang=en")
    assert response.status_code == 200
    assert "Dokumentspråk" in response.text
    assert "Faktura" in response.text


def test_invoice_document_renders_en_labels():
    project_id, invoice_id = _create_invoice()
    login()
    db = SessionLocal()
    try:
        invoice = db.get(Invoice, invoice_id)
        invoice.document_lang = "en"
        db.add(invoice)
        db.commit()
    finally:
        db.close()

    response = client.get(f"/projects/{project_id}/invoices/{invoice_id}")
    assert response.status_code == 200
    assert "Document language" in response.text
    assert "Invoice" in response.text
