from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.company_profile import CompanyProfile
from app.models.project import Project
from app.models.terms_template import TermsTemplate
from app.services.terms_templates import create_versioned_template
from tests.utils.document_factory import create_stable_document_fixture


client = TestClient(app)
settings = get_settings()


def login() -> None:
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
        follow_redirects=False,
    )


def _remove_company_and_terms() -> None:
    db = SessionLocal()
    try:
        db.query(CompanyProfile).delete()
        db.query(TermsTemplate).delete()
        db.commit()
    finally:
        db.close()


def _ensure_company_and_sv_terms() -> None:
    db = SessionLocal()
    try:
        profile = db.get(CompanyProfile, 1) or CompanyProfile(id=1)
        profile.legal_name = "Setup Test AB"
        db.add(profile)

        has_sv = db.query(TermsTemplate).filter(TermsTemplate.is_active.is_(True), TermsTemplate.lang == "sv").first()
        if not has_sv:
            create_versioned_template(
                db,
                segment="B2C",
                doc_type="OFFER",
                lang="sv",
                title="SV terms",
                body_text="SV terms body",
                is_active=True,
            )
        has_sv_invoice = db.query(TermsTemplate).filter(TermsTemplate.is_active.is_(True), TermsTemplate.lang == "sv", TermsTemplate.doc_type == "INVOICE").first()
        if not has_sv_invoice:
            create_versioned_template(
                db,
                segment="B2C",
                doc_type="INVOICE",
                lang="sv",
                title="SV invoice terms",
                body_text="SV invoice terms body",
                is_active=True,
            )
        db.commit()
    finally:
        db.close()


def test_onboarding_redirect_when_company_missing():
    _remove_company_and_terms()
    login()

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith("/onboarding")

    onboarding = client.get(response.headers["location"])
    assert onboarding.status_code == 200
    assert "Company" in onboarding.text


def test_onboarding_overview_lists_blockers():
    _remove_company_and_terms()
    login()

    response = client.get("/onboarding?step=overview")
    assert response.status_code == 200
    assert "BLOCK" in response.text
    assert "/onboarding?step=company" in response.text


def test_issue_offer_blocked_until_company_present():
    fixture = create_stable_document_fixture(enable_rot=False, issue_documents=False)

    db = SessionLocal()
    try:
        db.query(CompanyProfile).delete()
        db.commit()
    finally:
        db.close()

    login()
    blocked = client.post(f"/offers/{fixture.project_id}/issue", data={}, follow_redirects=False)
    assert blocked.status_code == 303
    assert blocked.headers["location"].endswith(f"/projects/{fixture.project_id}/offer")

    _ensure_company_and_sv_terms()
    allowed = client.post(f"/offers/{fixture.project_id}/issue", data={}, follow_redirects=False)
    assert allowed.status_code == 303

    db = SessionLocal()
    try:
        project = db.get(Project, fixture.project_id)
        assert project is not None
        assert project.offer_status == "issued"
    finally:
        db.close()


def test_onboarding_complete_when_blockers_resolved():
    _ensure_company_and_sv_terms()
    login()

    response = client.get("/onboarding")
    assert response.status_code == 200
    assert "Setup complete" in response.text


def teardown_module():
    _ensure_company_and_sv_terms()
