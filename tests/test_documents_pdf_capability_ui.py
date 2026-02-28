from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from tests.utils.document_factory import create_stable_document_fixture

client = TestClient(app)
settings = get_settings()


def login() -> None:
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def test_invoice_print_does_not_show_pdf_unavailable_when_playwright_available(monkeypatch):
    fixture = create_stable_document_fixture(enable_rot=False, issue_documents=False)
    login()
    monkeypatch.setattr(
        "app.routers.web_documents.invoice_pdf_capability",
        lambda: {
            "weasyprint_available": False,
            "playwright_available": True,
            "configured_engine": "auto",
            "active_engine": "playwright",
        },
    )

    response = client.get(f"/invoices/{fixture.invoice_id}/print?lang=en")

    assert response.status_code == 200
    assert "PDF engine fallback mode active" not in response.text
