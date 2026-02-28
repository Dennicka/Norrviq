from pathlib import Path

from tests.test_pdf_export import _create_offer_project, client, login
from app.services import pdf_renderer


def test_pdf_engine_auto_uses_weasyprint_when_available(monkeypatch):
    monkeypatch.setenv("PDF_ENGINE", "auto")
    monkeypatch.setattr(pdf_renderer, "is_weasyprint_available", lambda: True)
    monkeypatch.setattr(pdf_renderer, "is_playwright_available", lambda: True)
    monkeypatch.setattr(pdf_renderer, "_render_with_weasyprint", lambda **_: b"%PDF-WEASY")
    monkeypatch.setattr(pdf_renderer, "_render_with_playwright", lambda **_: b"%PDF-PW")

    result = pdf_renderer.render_pdf_from_html_with_engine(
        html="<html><body>ok</body></html>",
        base_url=Path.cwd(),
        stylesheet_path=None,
    )

    assert result.engine == "weasyprint"
    assert result.pdf_bytes.startswith(b"%PDF-WEASY")


def test_pdf_engine_auto_falls_back_to_playwright_when_weasyprint_errors(monkeypatch):
    monkeypatch.setenv("PDF_ENGINE", "auto")
    monkeypatch.setattr(pdf_renderer, "is_weasyprint_available", lambda: True)
    monkeypatch.setattr(pdf_renderer, "is_playwright_available", lambda: True)

    def _boom(**_):
        raise Exception("boom")

    monkeypatch.setattr(pdf_renderer, "_render_with_weasyprint", _boom)
    monkeypatch.setattr(pdf_renderer, "_render_with_playwright", lambda **_: b"%PDF-PW")

    result = pdf_renderer.render_pdf_from_html_with_engine(
        html="<html><body>ok</body></html>",
        base_url=Path.cwd(),
        stylesheet_path=None,
    )

    assert result.engine == "playwright"
    assert result.pdf_bytes.startswith(b"%PDF-PW")


def test_pdf_engine_configured_playwright_falls_back_to_fallback_when_unavailable(monkeypatch):
    monkeypatch.setenv("PDF_ENGINE", "playwright")
    monkeypatch.setattr(pdf_renderer, "is_playwright_available", lambda: False)

    result = pdf_renderer.render_pdf_from_html_with_engine(
        html="<html><body>Portable PDF fallback</body></html>",
        base_url=Path.cwd(),
        stylesheet_path=None,
    )

    assert result.engine == "fallback_pdf"
    assert result.pdf_bytes.startswith(b"%PDF")
    assert b"Portable PDF fallback" in result.pdf_bytes


def test_offer_pdf_has_engine_header():
    project_id = _create_offer_project(issued=False)
    login()

    response = client.get(f"/offers/{project_id}/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers.get("X-PDF-Engine") in {"weasyprint", "playwright", "fallback_pdf"}
