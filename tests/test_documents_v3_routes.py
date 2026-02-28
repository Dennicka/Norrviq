from tests.test_invoice_pdf_fallback import _create_invoice, _create_offer_project, client, login


def test_documents_page_route_redirects_to_documents_tab():
    project_id = _create_offer_project()
    login()

    response = client.get(f"/projects/{project_id}/documents", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/projects/{project_id}?tab=documents"


def test_offer_preview_mode_pdf_redirects_to_offer_pdf():
    project_id = _create_offer_project()
    login()

    response = client.get(f"/offers/{project_id}/preview?lang=ru&mode=pdf", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/offers/{project_id}/pdf?lang=ru"


def test_invoice_preview_mode_html_redirects_to_project_invoice_page():
    project_id, invoice_id = _create_invoice()
    login()

    response = client.get(f"/invoices/{invoice_id}/preview?lang=sv&mode=html", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/projects/{project_id}/invoices/{invoice_id}?lang=sv"
