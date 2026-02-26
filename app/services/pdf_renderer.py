import logging
from pathlib import Path

from collections.abc import Callable

from app.services.pdf_engine import is_pdf_engine_available
from app.services.pdf_export import render_pdf_from_html

logger = logging.getLogger("app.pdf")


def is_weasyprint_available() -> bool:
    return is_pdf_engine_available()


def invoice_pdf_capability() -> dict[str, str | bool]:
    available = is_weasyprint_available()
    return {
        "weasyprint_available": available,
        "active_engine": "weasyprint" if available else "print_html_fallback",
    }


def render_invoice_pdf(
    invoice_id: int,
    language: str,
    *,
    html: str,
    base_url: str | Path,
    stylesheet_path: str | Path | None = None,
    render_pdf: Callable[..., bytes] = render_pdf_from_html,
) -> bytes | None:
    if not is_weasyprint_available():
        logger.warning(
            "invoice_pdf_fallback_mode invoice_id=%s lang=%s reason=weasyprint_unavailable",
            invoice_id,
            language,
        )
        return None
    try:
        return render_pdf(html=html, base_url=base_url, stylesheet_path=stylesheet_path)
    except RuntimeError:
        logger.exception(
            "invoice_pdf_fallback_mode invoice_id=%s lang=%s reason=runtime_error",
            invoice_id,
            language,
        )
        return None
