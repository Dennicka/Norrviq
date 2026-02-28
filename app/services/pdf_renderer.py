from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

from app.services.pdf_fallback import html_to_plain_text, render_pdf_fallback_from_html

logger = logging.getLogger("app.pdf")

PdfBackend = Literal["auto", "weasyprint", "reportlab"]


def _normalize_backend(raw: str | None) -> PdfBackend:
    backend = (raw or "auto").strip().lower()
    if backend in {"auto", "weasyprint", "reportlab"}:
        return backend  # type: ignore[return-value]
    return "auto"


def get_pdf_backend_mode() -> PdfBackend:
    # PDF_ENGINE is kept for backward compatibility.
    legacy = (os.getenv("PDF_ENGINE") or "").strip().lower()
    if legacy in {"html_only", "playwright"}:
        return "reportlab"
    return _normalize_backend(os.getenv("PDF_BACKEND") or os.getenv("PDF_ENGINE"))


def is_weasyprint_available() -> bool:
    try:
        from weasyprint import HTML

        HTML(string="<html><body>ok</body></html>", base_url=str(Path.cwd())).write_pdf()
        return True
    except Exception:
        return False


def _render_with_weasyprint(*, html: str, base_url: str | Path, stylesheet_path: str | Path | None = None) -> bytes:
    from weasyprint import CSS, HTML

    document = HTML(string=html, base_url=str(base_url))
    stylesheets = [CSS(filename=str(stylesheet_path))] if stylesheet_path else None
    return document.write_pdf(stylesheets=stylesheets)


def _register_reportlab_font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_name = "Helvetica"
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            pdfmetrics.registerFont(TTFont("PortableUnicode", str(candidate)))
            font_name = "PortableUnicode"
            break
    return font_name


def _render_with_reportlab(*, html: str, base_url: str | Path, stylesheet_path: str | Path | None = None) -> bytes:
    from io import BytesIO

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ModuleNotFoundError:
        return render_pdf_fallback_from_html(html, title="Document")

    _ = base_url, stylesheet_path

    text = html_to_plain_text(html)
    lines = [line.strip() for line in text.splitlines() if line.strip()] or ["Document"]

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
        title="Document",
    )
    styles = getSampleStyleSheet()
    font_name = _register_reportlab_font()
    normal = ParagraphStyle(
        "PortableNormal",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10,
        leading=13,
        spaceAfter=2,
    )
    title_style = ParagraphStyle(
        "PortableTitle",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=16,
        leading=20,
        spaceAfter=8,
    )

    story = [Paragraph(lines[0], title_style), Spacer(1, 4)]
    for line in lines[1:]:
        story.append(Paragraph(line, normal))

    doc.build(story)
    return buffer.getvalue()


def render_pdf(html: str, base_url: str | Path, stylesheet_path: str | Path | None = None) -> bytes:
    backend = get_pdf_backend_mode()
    if backend == "weasyprint":
        return _render_with_weasyprint(html=html, base_url=base_url, stylesheet_path=stylesheet_path)
    if backend == "reportlab":
        return _render_with_reportlab(html=html, base_url=base_url, stylesheet_path=stylesheet_path)

    if is_weasyprint_available():
        try:
            return _render_with_weasyprint(html=html, base_url=base_url, stylesheet_path=stylesheet_path)
        except Exception:
            logger.exception("PDF auto backend: WeasyPrint failed, falling back to ReportLab")
    return _render_with_reportlab(html=html, base_url=base_url, stylesheet_path=stylesheet_path)


def invoice_pdf_capability() -> dict[str, str | bool]:
    configured = get_pdf_backend_mode()
    weasy = is_weasyprint_available()
    active = "weasyprint" if configured == "weasyprint" else ("reportlab" if configured == "reportlab" else ("weasyprint" if weasy else "reportlab"))
    return {
        "weasyprint_available": weasy,
        "playwright_available": False,
        "configured_engine": configured,
        "active_engine": active,
    }


def render_invoice_pdf(invoice_id: int, language: str, *, html: str, base_url: str | Path, stylesheet_path: str | Path | None = None) -> bytes:
    pdf_bytes = render_pdf(html=html, base_url=base_url, stylesheet_path=stylesheet_path)
    logger.info("invoice_pdf_rendered invoice_id=%s lang=%s bytes=%s", invoice_id, language, len(pdf_bytes))
    return pdf_bytes
