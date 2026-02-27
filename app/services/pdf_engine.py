from app.services.pdf_renderer import PDFEngineUnavailableError, is_weasyprint_available


def is_pdf_engine_available() -> bool:
    return is_weasyprint_available()


__all__ = ["PDFEngineUnavailableError", "is_pdf_engine_available"]
