from __future__ import annotations

from pathlib import Path

from app.services.pdf_renderer import render_pdf


class PDFEngineUnavailableError(RuntimeError):
    """Compatibility error kept for legacy imports."""


def render_pdf_from_html(*, html: str, base_url: str | Path, stylesheet_path: str | Path | None = None) -> bytes:
    return render_pdf(html=html, base_url=base_url, stylesheet_path=stylesheet_path)
