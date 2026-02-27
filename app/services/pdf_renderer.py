from __future__ import annotations

import logging
from collections.abc import Callable
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin

logger = logging.getLogger("app.pdf")

PdfEngine = Literal["auto", "weasyprint", "playwright", "html_only"]


class PDFEngineUnavailableError(RuntimeError):
    """Raised when no configured PDF backend can render the document."""


def _normalize_engine(raw: str | None) -> PdfEngine:
    engine = (raw or "auto").strip().lower()
    if engine in {"weasyprint", "playwright", "html_only", "auto"}:
        return engine  # type: ignore[return-value]
    return "auto"


def get_pdf_engine_mode() -> PdfEngine:
    return _normalize_engine(os.getenv("PDF_ENGINE"))


def _ensure_base_href(html: str, base_url: str | Path) -> str:
    base = str(base_url)
    if "<base " in html.lower():
        return html
    if "<head" in html.lower():
        return html.replace("<head>", f'<head><base href="{base}/">', 1)
    return f'<head><base href="{base}/"></head>{html}'


def _render_with_weasyprint(*, html: str, base_url: str | Path, stylesheet_path: str | Path | None) -> bytes:
    from weasyprint import CSS, HTML

    document = HTML(string=html, base_url=str(base_url))
    stylesheets = [CSS(filename=str(stylesheet_path))] if stylesheet_path else None
    return document.write_pdf(stylesheets=stylesheets)


def _render_with_playwright(*, html: str, base_url: str | Path, stylesheet_path: str | Path | None) -> bytes:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    prepared_html = _ensure_base_href(html, base_url)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.set_content(prepared_html, wait_until="networkidle")
            if stylesheet_path:
                stylesheet_uri = urljoin(f"file://{Path(stylesheet_path).resolve()}", "")
                page.add_style_tag(url=stylesheet_uri)
            pdf_bytes = page.pdf(print_background=True, prefer_css_page_size=True)
            browser.close()
            return pdf_bytes
    except PlaywrightError as exc:  # pragma: no cover - runtime specific
        raise PDFEngineUnavailableError("Playwright backend is unavailable") from exc


def is_weasyprint_available() -> bool:
    try:
        _render_with_weasyprint(html="<html><body>ok</body></html>", base_url=Path.cwd(), stylesheet_path=None)
        return True
    except Exception:
        return False


def is_playwright_available() -> bool:
    try:
        _render_with_playwright(html="<html><body>ok</body></html>", base_url=Path.cwd(), stylesheet_path=None)
        return True
    except Exception:
        return False


def invoice_pdf_capability() -> dict[str, str | bool]:
    mode = get_pdf_engine_mode()
    weasy = is_weasyprint_available()
    playwright = is_playwright_available()
    if mode == "weasyprint":
        active = "weasyprint" if weasy else "print_html_fallback"
    elif mode == "playwright":
        active = "playwright" if playwright else "print_html_fallback"
    elif mode == "html_only":
        active = "print_html_fallback"
    else:
        active = "weasyprint" if weasy else ("playwright" if playwright else "print_html_fallback")
    return {
        "weasyprint_available": weasy,
        "playwright_available": playwright,
        "configured_engine": mode,
        "active_engine": active,
    }


def render_pdf_from_html(*, html: str, base_url: str | Path, stylesheet_path: str | Path | None = None) -> bytes:
    mode = get_pdf_engine_mode()
    attempts: list[str]
    if mode == "auto":
        attempts = ["weasyprint", "playwright"]
    elif mode == "html_only":
        attempts = []
    else:
        attempts = [mode]

    errors: list[str] = []
    for engine in attempts:
        try:
            if engine == "weasyprint":
                if not is_weasyprint_available():
                    errors.append("weasyprint: unavailable")
                    continue
                return _render_with_weasyprint(html=html, base_url=base_url, stylesheet_path=stylesheet_path)
            if engine == "playwright":
                if not is_playwright_available():
                    errors.append("playwright: unavailable")
                    continue
                return _render_with_playwright(html=html, base_url=base_url, stylesheet_path=stylesheet_path)
        except Exception as exc:  # pragma: no cover - runtime specific
            logger.warning("pdf engine failed engine=%s error=%s", engine, exc)
            errors.append(f"{engine}: {exc}")

    message = "PDF rendering unavailable. Set PDF_ENGINE=playwright and run `make pdf-install` or use HTML print view."
    if errors:
        message = f"{message} Details: {'; '.join(errors)}"
    raise PDFEngineUnavailableError(message)


def render_invoice_pdf(
    invoice_id: int,
    language: str,
    *,
    html: str,
    base_url: str | Path,
    stylesheet_path: str | Path | None = None,
    render_pdf: Callable[..., bytes] = render_pdf_from_html,
) -> bytes | None:
    try:
        return render_pdf(html=html, base_url=base_url, stylesheet_path=stylesheet_path)
    except (PDFEngineUnavailableError, RuntimeError):
        logger.warning(
            "invoice_pdf_fallback_mode invoice_id=%s lang=%s reason=engine_unavailable",
            invoice_id,
            language,
        )
        return None
