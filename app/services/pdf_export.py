from pathlib import Path


def render_pdf_from_html(*, html: str, base_url: str | Path) -> bytes:
    try:
        from weasyprint import HTML
    except Exception as exc:  # pragma: no cover - runtime environment specific
        raise RuntimeError("PDF engine is not available") from exc

    document = HTML(string=html, base_url=str(base_url))
    return document.write_pdf()
