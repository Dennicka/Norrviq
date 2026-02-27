from app.services.pdf_export import PDFEngineUnavailableError


def is_pdf_engine_available() -> bool:
    return True


__all__ = ["PDFEngineUnavailableError", "is_pdf_engine_available"]
