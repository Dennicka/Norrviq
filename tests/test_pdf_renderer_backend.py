from pathlib import Path

from app.services import pdf_renderer


def test_render_pdf_auto_falls_back_to_reportlab(monkeypatch):
    monkeypatch.setenv("PDF_BACKEND", "auto")
    monkeypatch.delenv("PDF_ENGINE", raising=False)
    monkeypatch.setattr(pdf_renderer, "is_weasyprint_available", lambda: False)

    used = {"reportlab": False}

    def _fake_reportlab(*, html: str, base_url: str | Path, stylesheet_path: str | Path | None = None) -> bytes:
        used["reportlab"] = True
        return b"%PDF-1.4 fallback"

    monkeypatch.setattr(pdf_renderer, "_render_with_reportlab", _fake_reportlab)

    payload = pdf_renderer.render_pdf("<h1>Invoice</h1>", base_url=Path.cwd())

    assert used["reportlab"] is True
    assert payload.startswith(b"%PDF")


def test_pdf_backend_env_reportlab(monkeypatch):
    monkeypatch.setenv("PDF_BACKEND", "reportlab")
    assert pdf_renderer.get_pdf_backend_mode() == "reportlab"
