from pathlib import Path


def render_pdf_from_html(*, html: str, base_url: str | Path, stylesheet_path: str | Path | None = None) -> bytes:
    try:
        from weasyprint import CSS, HTML
    except Exception as exc:  # pragma: no cover - runtime environment specific
        raise RuntimeError("PDF engine is not available") from exc

    document = HTML(string=html, base_url=str(base_url))
    stylesheets = [CSS(filename=str(stylesheet_path))] if stylesheet_path else None
    return document.write_pdf(stylesheets=stylesheets)
