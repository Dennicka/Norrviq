from tests.test_invoice_pdf_fallback import _create_invoice, login, client


def test_invoice_pdf_html_only_mode_still_returns_pdf(monkeypatch):
    _, invoice_id = _create_invoice()
    login()
    monkeypatch.setenv("PDF_ENGINE", "html_only")

    response = client.get(f"/invoices/{invoice_id}/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_invoice_pdf_auto_mode_returns_pdf(monkeypatch):
    _, invoice_id = _create_invoice()
    login()
    monkeypatch.setenv("PDF_ENGINE", "auto")

    response = client.get(f"/invoices/{invoice_id}/pdf")

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
