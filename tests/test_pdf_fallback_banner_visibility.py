from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from tests.utils.document_factory import create_stable_document_fixture

client = TestClient(app)
settings = get_settings()


FALLBACK_BANNER_SV = "PDF-motorns reservläge är aktivt"


def login() -> None:
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def _patch_pdf_capability(monkeypatch, *, active_engine: str) -> None:
    payload = {
        "weasyprint_available": False,
        "playwright_available": active_engine == "playwright",
        "configured_engine": "auto",
        "active_engine": active_engine,
    }
    monkeypatch.setattr("app.routers.web_invoices.invoice_pdf_capability", lambda: payload)
    monkeypatch.setattr("app.routers.web_documents.invoice_pdf_capability", lambda: payload)


def test_invoice_document_hides_banner_when_active_engine_playwright(monkeypatch):
    fixture = create_stable_document_fixture(issue_documents=True, pricing_mode="PER_M2", enable_rot=False)
    login()
    _patch_pdf_capability(monkeypatch, active_engine="playwright")

    response = client.get(f"/projects/{fixture.project_id}/invoices/{fixture.invoice_id}?lang=sv")

    assert response.status_code == 200
    assert FALLBACK_BANNER_SV not in response.text


def test_invoice_document_shows_banner_when_active_engine_fallback(monkeypatch):
    fixture = create_stable_document_fixture(issue_documents=True, pricing_mode="PER_M2", enable_rot=False)
    login()
    _patch_pdf_capability(monkeypatch, active_engine="fallback_pdf")

    response = client.get(f"/projects/{fixture.project_id}/invoices/{fixture.invoice_id}?lang=sv")

    assert response.status_code == 200
    assert FALLBACK_BANNER_SV in response.text


def test_invoice_print_banner_visibility_tracks_active_engine(monkeypatch):
    fixture = create_stable_document_fixture(issue_documents=True, pricing_mode="PER_M2", enable_rot=False)
    login()

    _patch_pdf_capability(monkeypatch, active_engine="playwright")
    response_playwright = client.get(f"/invoices/{fixture.invoice_id}/print?lang=sv")
    assert response_playwright.status_code == 200
    assert FALLBACK_BANNER_SV not in response_playwright.text

    _patch_pdf_capability(monkeypatch, active_engine="fallback_pdf")
    response_fallback = client.get(f"/invoices/{fixture.invoice_id}/print?lang=sv")
    assert response_fallback.status_code == 200
    assert FALLBACK_BANNER_SV in response_fallback.text
