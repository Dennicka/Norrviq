from __future__ import annotations

from pathlib import Path


class PDFEngineUnavailableError(RuntimeError):
    """Raised when the configured PDF engine cannot render in this runtime."""


def is_pdf_engine_available() -> bool:
    try:
        from weasyprint import HTML

        HTML(string="<html><body>ok</body></html>", base_url=str(Path.cwd())).write_pdf()
        return True
    except Exception:
        return False
