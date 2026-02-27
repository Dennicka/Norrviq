from __future__ import annotations

from pathlib import Path

from app.services.pdf_fallback import render_pdf_fallback_from_html


class PDFEngineUnavailableError(RuntimeError):
    """Compatibility error kept for legacy imports."""


def render_pdf_from_html(*, html: str, base_url: str | Path, stylesheet_path: str | Path | None = None) -> bytes:
    try:
        from weasyprint import CSS, HTML

        document = HTML(string=html, base_url=str(base_url))
        stylesheets = [CSS(filename=str(stylesheet_path))] if stylesheet_path else None
        return document.write_pdf(stylesheets=stylesheets)
    except Exception:
        return render_pdf_fallback_from_html(html, title="Document")
