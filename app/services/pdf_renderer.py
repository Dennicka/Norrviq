from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.services.pdf_export import render_pdf_from_html as export_render_pdf_from_html
from app.services.pdf_fallback import render_pdf_fallback_from_html

logger = logging.getLogger("app.pdf")

PdfEngine = Literal["auto", "weasyprint", "playwright", "html_only"]
PdfRenderedEngine = Literal["weasyprint", "playwright", "fallback_pdf"]


class PDFEngineUnavailableError(RuntimeError):
    """Raised when the configured PDF backend is unavailable."""


@dataclass
class PdfRenderResult:
    pdf_bytes: bytes
    engine: PdfRenderedEngine
    warnings: list[str] = field(default_factory=list)


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


def _render_with_weasyprint(*, html: str, base_url: str | Path, stylesheet_path: str | Path | None = None) -> bytes:
    return export_render_pdf_from_html(html=html, base_url=base_url, stylesheet_path=stylesheet_path)


def _strip_stylesheet_links(html: str) -> str:
    pattern = re.compile(r"<link\b[^>]*\brel\s*=\s*['\"]?stylesheet['\"]?[^>]*>", flags=re.IGNORECASE)
    return re.sub(pattern, "", html)


def _render_with_playwright(*, html: str, stylesheet_path: Path | None = None) -> bytes:
    from playwright.sync_api import sync_playwright

    sanitized_html = _strip_stylesheet_links(html)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            try:
                page.set_content(sanitized_html, wait_until="load")
                if stylesheet_path and stylesheet_path.exists():
                    css_content = stylesheet_path.read_text(encoding="utf-8")
                    page.add_style_tag(content=css_content)
                return page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
            finally:
                page.close()
        finally:
            browser.close()


def render_pdf_from_html_with_engine(*, html: str, base_url: str | Path, stylesheet_path: str | Path | None = None) -> PdfRenderResult:
    mode = get_pdf_engine_mode()
    css_path = Path(stylesheet_path) if stylesheet_path else None
    warnings: list[str] = []

    def _fallback(reason: str) -> PdfRenderResult:
        warnings.append(reason)
        return PdfRenderResult(
            pdf_bytes=render_pdf_fallback_from_html(html, title="Document"),
            engine="fallback_pdf",
            warnings=warnings,
        )

    def _try_weasyprint() -> PdfRenderResult:
        if not is_weasyprint_available():
            raise PDFEngineUnavailableError("weasyprint unavailable")
        return PdfRenderResult(
            pdf_bytes=_render_with_weasyprint(html=html, base_url=base_url, stylesheet_path=stylesheet_path),
            engine="weasyprint",
            warnings=warnings,
        )

    def _try_playwright() -> PdfRenderResult:
        if not is_playwright_available():
            raise PDFEngineUnavailableError("playwright unavailable")
        return PdfRenderResult(
            pdf_bytes=_render_with_playwright(html=html, stylesheet_path=css_path),
            engine="playwright",
            warnings=warnings,
        )

    if mode == "html_only":
        return _fallback("PDF_ENGINE=html_only")

    if mode == "weasyprint":
        try:
            return _try_weasyprint()
        except Exception as exc:
            logger.exception("weasyprint_render_failed mode=weasyprint")
            return _fallback(f"weasyprint failed: {exc}")

    if mode == "playwright":
        try:
            return _try_playwright()
        except Exception as exc:
            logger.exception("playwright_render_failed mode=playwright")
            return _fallback(f"playwright failed: {exc}")

    try:
        return _try_weasyprint()
    except Exception as exc:
        warnings.append(f"weasyprint failed: {exc}")
        logger.exception("weasyprint_render_failed mode=auto")

    try:
        return _try_playwright()
    except Exception as exc:
        logger.exception("playwright_render_failed mode=auto")
        return _fallback(f"playwright failed: {exc}")


def render_pdf_from_html(*, html: str, base_url: str | Path, stylesheet_path: str | Path | None = None) -> bytes:
    return render_pdf_from_html_with_engine(html=html, base_url=base_url, stylesheet_path=stylesheet_path).pdf_bytes


def render_invoice_pdf(
    invoice_id: int,
    language: str,
    *,
    html: str,
    base_url: str | Path,
    stylesheet_path: str | Path | None = None,
    render_pdf: Callable[..., PdfRenderResult] = render_pdf_from_html_with_engine,
) -> PdfRenderResult:
    result = render_pdf(html=html, base_url=base_url, stylesheet_path=stylesheet_path)
    logger.info("invoice_pdf_rendered invoice_id=%s lang=%s bytes=%s engine=%s", invoice_id, language, len(result.pdf_bytes), result.engine)
    return result
