from decimal import Decimal

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.company_profile import get_or_create_company_profile
from app.models.invoice import Invoice
from app.models.project import Project, ProjectWorkItem
from app.services.commercial_snapshot import DOC_TYPE_OFFER, read_commercial_snapshot
from app.services.document_numbering import finalize_offer
from app.services.offer_commercial import compute_offer_commercial
from tests.utils.document_factory import create_stable_document_fixture

client = TestClient(app)
settings = get_settings()


def login() -> None:
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def test_document_issue_freezes_totals():
    fixture = create_stable_document_fixture(enable_rot=False, issue_documents=False, pricing_mode="HOURLY")

    db = SessionLocal()
    try:
        project = db.get(Project, fixture.project_id)
        assert project is not None

        # Issue creates immutable commercial snapshot used for issued offer rendering.
        profile = get_or_create_company_profile(db)
        finalize_offer(db, project_id=project.id, user_id="tests", profile=profile)
        db.flush()

        snapshot_before = read_commercial_snapshot(db, doc_type=DOC_TYPE_OFFER, doc_id=project.id)
        assert snapshot_before is not None
        frozen_total = Decimal(str(snapshot_before["totals"]["price_inc_vat"]))

        item = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project.id).first()
        assert item is not None
        item.calculated_hours = Decimal("48.00")
        project.pricing.hourly_rate_override = Decimal("900.00")
        db.flush()

        recomputed = compute_offer_commercial(db, project.id, lang="sv")
        assert recomputed.price_inc_vat != frozen_total

        snapshot_after = read_commercial_snapshot(db, doc_type=DOC_TYPE_OFFER, doc_id=project.id)
        assert snapshot_after is not None
        assert Decimal(str(snapshot_after["totals"]["price_inc_vat"])) == frozen_total
    finally:
        db.rollback()
        db.close()


def test_offer_print_returns_200_and_contains_key_fields_ru():
    fixture = create_stable_document_fixture(enable_rot=False, issue_documents=False)
    login()

    response = client.get(f"/offers/{fixture.project_id}/print?lang=ru")

    assert response.status_code == 200
    assert "Коммерческое предложение" in response.text
    assert "Итого" in response.text
    assert "MOMS" in response.text


def test_invoice_print_returns_200_and_contains_key_fields_sv():
    fixture = create_stable_document_fixture(enable_rot=False, issue_documents=False)
    login()

    db = SessionLocal()
    try:
        invoice = db.get(Invoice, fixture.invoice_id)
        assert invoice is not None
        invoice.document_lang = "sv"
        db.add(invoice)
        db.commit()
    finally:
        db.close()

    response = client.get(f"/invoices/{fixture.invoice_id}/print?lang=sv")

    assert response.status_code == 200
    assert "Faktura" in response.text
    assert "Moms" in response.text or "MOMS" in response.text
    assert "Totalt" in response.text or "Att betala" in response.text


def test_pdf_endpoint_returns_pdf_when_engine_missing(monkeypatch):
    fixture = create_stable_document_fixture(enable_rot=False, issue_documents=False)
    login()
    monkeypatch.setattr("app.services.pdf_renderer.is_weasyprint_available", lambda: False)

    response = client.get(f"/invoices/{fixture.invoice_id}/pdf", follow_redirects=False)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_issue_sets_status_issued_and_number_assigned():
    fixture = create_stable_document_fixture(enable_rot=False, issue_documents=False)
    login()

    response = client.post(f"/offers/{fixture.project_id}/issue", follow_redirects=False)
    assert response.status_code == 303

    db = SessionLocal()
    try:
        project = db.get(Project, fixture.project_id)
        assert project is not None
        assert project.offer_status == "issued"
        assert project.offer_number
    finally:
        db.close()
