from datetime import date

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.client import Client
from app.models.company_profile import get_or_create_company_profile
from app.models.invoice import Invoice
from app.models.project import Project
from app.models.user import User
from app.security import hash_password
from app.services.terms_templates import DOC_TYPE_INVOICE, DOC_TYPE_OFFER, create_versioned_template, resolve_terms_template

client = TestClient(app)
settings = get_settings()


def _login(username: str, password: str):
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


def _mk_project_with_client(segment: str = "B2C") -> tuple[int, int]:
    db = SessionLocal()
    try:
        c = Client(name=f"C-{segment}", client_segment=segment)
        db.add(c)
        db.flush()
        p = Project(name=f"P-{segment}", client_id=c.id)
        db.add(p)
        db.commit()
        return c.id, p.id
    finally:
        db.close()


def test_terms_template_versioning_creates_new_version():
    db = SessionLocal()
    try:
        first = create_versioned_template(
            db, segment="B2C", doc_type="OFFER", lang="sv", title="v1", body_text="body1"
        )
        second = create_versioned_template(
            db, segment="B2C", doc_type="OFFER", lang="sv", title="v2", body_text="body2"
        )
        db.commit()
        assert first.version == 1
        assert second.version == 2
    finally:
        db.close()


def test_terms_templates_admin_only():
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == "viewer-terms@example.com").first():
            db.add(User(email="viewer-terms@example.com", password_hash=hash_password("pw"), role="viewer"))
            db.commit()
    finally:
        db.close()

    client.get("/logout")
    _login("viewer-terms@example.com", "pw")
    response = client.get("/settings/terms")
    assert response.status_code == 403


def test_offer_finalize_snapshots_terms_and_is_immutable():
    _login(settings.admin_email, settings.admin_password)
    _, project_id = _mk_project_with_client("B2C")

    db = SessionLocal()
    try:
        create_versioned_template(db, segment="B2C", doc_type="OFFER", lang="sv", title="Offer V1", body_text="Body V1")
        db.commit()
    finally:
        db.close()

    r1 = client.post(f"/offers/{project_id}/finalize", data={"terms_lang": "sv"}, follow_redirects=False)
    assert r1.status_code == 303

    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        assert project.offer_terms_snapshot_title == "Offer V1"
        create_versioned_template(db, segment="B2C", doc_type="OFFER", lang="sv", title="Offer V2", body_text="Body V2")
        db.commit()
    finally:
        db.close()

    r2 = client.post(f"/offers/{project_id}/finalize", data={"terms_lang": "sv"}, follow_redirects=False)
    assert r2.status_code == 303

    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        assert project.offer_terms_snapshot_title == "Offer V1"
    finally:
        db.close()


def test_invoice_finalize_snapshots_terms_and_is_immutable():
    _login(settings.admin_email, settings.admin_password)
    _, project_id = _mk_project_with_client("B2C")

    db = SessionLocal()
    try:
        inv = Invoice(
            project_id=project_id,
            invoice_number=None,
            issue_date=date.today(),
            status="draft",
            work_sum_without_moms=0,
            moms_amount=0,
            rot_amount=0,
            client_pays_total=0,
        )
        db.add(inv)
        create_versioned_template(db, segment="B2C", doc_type="INVOICE", lang="sv", title="Inv V1", body_text="IBody1")
        db.commit()
        invoice_id = inv.id
    finally:
        db.close()

    r1 = client.post(f"/invoices/{invoice_id}/finalize", data={"terms_lang": "sv"}, follow_redirects=False)
    assert r1.status_code == 303

    db = SessionLocal()
    try:
        invoice = db.get(Invoice, invoice_id)
        assert invoice.invoice_terms_snapshot_title == "Inv V1"
        create_versioned_template(db, segment="B2C", doc_type="INVOICE", lang="sv", title="Inv V2", body_text="IBody2")
        db.commit()
    finally:
        db.close()

    r2 = client.post(f"/invoices/{invoice_id}/finalize", data={"terms_lang": "sv"}, follow_redirects=False)
    assert r2.status_code == 303

    db = SessionLocal()
    try:
        invoice = db.get(Invoice, invoice_id)
        assert invoice.invoice_terms_snapshot_title == "Inv V1"
    finally:
        db.close()


def test_template_selection_fallback_to_sv():
    db = SessionLocal()
    try:
        c = Client(name="fallback", client_segment="B2C")
        db.add(c)
        db.flush()
        profile = get_or_create_company_profile(db)
        create_versioned_template(db, segment="B2C", doc_type="OFFER", lang="sv", title="SV", body_text="S")
        db.commit()
        t = resolve_terms_template(db, profile=profile, client=c, doc_type=DOC_TYPE_OFFER, lang="en")
        assert t is not None
        assert t.lang == "sv"
    finally:
        db.close()


def test_client_segment_drives_template_selection():
    db = SessionLocal()
    try:
        c = Client(name="seg", client_segment="B2B")
        db.add(c)
        db.flush()
        profile = get_or_create_company_profile(db)
        create_versioned_template(db, segment="B2C", doc_type="INVOICE", lang="sv", title="B2C", body_text="1")
        create_versioned_template(db, segment="B2B", doc_type="INVOICE", lang="sv", title="B2B", body_text="2")
        db.commit()
        t = resolve_terms_template(db, profile=profile, client=c, doc_type=DOC_TYPE_INVOICE, lang="sv")
        assert t is not None
        assert t.segment == "B2B"
    finally:
        db.close()
