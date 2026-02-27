from __future__ import annotations

import logging
from collections.abc import Callable
import os
from pathlib import Path
from typing import Literal

from app.services.pdf_export import render_pdf_from_html as export_render_pdf_from_html

logger = logging.getLogger("app.pdf")

PdfEngine = Literal["auto", "weasyprint", "playwright", "html_only"]


class PDFEngineUnavailableError(RuntimeError):
    """Raised when the configured PDF backend is unavailable."""


def _normalize_engine(raw: str | None) -> PdfEngine:
    engine = (raw or "auto").strip().lower()
    if engine in {"weasyprint", "playwright", "html_only", "auto"}:
        return engine  # type: ignore[return-value]
    return "auto"


def get_pdf_engine_mode() -> PdfEngine:
    return _normalize_engine(os.getenv("PDF_ENGINE"))


def is_weasyprint_available() -> bool:
    try:
        from weasyprint import HTML

        HTML(string="<html><body>ok</body></html>", base_url=str(Path.cwd())).write_pdf()
        return True
    except Exception:
        return False


def is_playwright_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            browser.close()
        return True
    except Exception:
        return False


def invoice_pdf_capability() -> dict[str, str | bool]:
    mode = get_pdf_engine_mode()
    weasy = is_weasyprint_available()
    playwright = is_playwright_available()
    if mode == "weasyprint":
        active = "weasyprint" if weasy else "fallback_pdf"
    elif mode == "playwright":
        active = "playwright" if playwright else "fallback_pdf"
    elif mode == "html_only":
        active = "fallback_pdf"
    else:
        active = "weasyprint" if weasy else ("playwright" if playwright else "fallback_pdf")
    return {
        "weasyprint_available": weasy,
        "playwright_available": playwright,
        "configured_engine": mode,
        "active_engine": active,
    }


def render_pdf_from_html(*, html: str, base_url: str | Path, stylesheet_path: str | Path | None = None) -> bytes:
    return export_render_pdf_from_html(html=html, base_url=base_url, stylesheet_path=stylesheet_path)


def render_invoice_pdf(
    invoice_id: int,
    language: str,
    *,
    html: str,
    base_url: str | Path,
    stylesheet_path: str | Path | None = None,
    render_pdf: Callable[..., bytes] = render_pdf_from_html,
) -> bytes:
    pdf_bytes = render_pdf(html=html, base_url=base_url, stylesheet_path=stylesheet_path)
    logger.info("invoice_pdf_rendered invoice_id=%s lang=%s bytes=%s", invoice_id, language, len(pdf_bytes))
    return pdf_bytes
