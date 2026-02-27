from tests.test_invoice_pdf_fallback import _create_invoice, login, client


def test_invoice_pdf_html_only_fallback_no_500(monkeypatch):
    _, invoice_id = _create_invoice()
    login()
    monkeypatch.setenv("PDF_ENGINE", "html_only")

    response = client.get(f"/invoices/{invoice_id}/pdf")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_invoice_pdf_playwright_returns_pdf(monkeypatch):
    _, invoice_id = _create_invoice()
    login()
    monkeypatch.setenv("PDF_ENGINE", "playwright")
    monkeypatch.setattr("app.services.pdf_renderer._render_with_playwright", lambda **_: b"%PDF-1.7 fake")

    response = client.get(f"/invoices/{invoice_id}/pdf")

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
