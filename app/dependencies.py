from typing import Callable, Optional

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal
from .i18n import make_t

settings = get_settings()
templates = Jinja2Templates(directory="app/templates")


async def get_current_lang(request: Request) -> str:
    lang = request.cookies.get("lang", settings.default_lang)
    if lang not in ("ru", "sv"):
        lang = settings.default_lang
    return lang


def template_context(request: Request, lang: str) -> dict:
    translator: Callable[[str], str] = make_t(lang)
    current_user = request.session.get("user_email") if hasattr(request, "session") else None
    flash_message: Optional[dict] = None
    if hasattr(request, "session"):
        flash_message = request.session.pop("flash_message", None)

    return {
        "request": request,
        "lang": lang,
        "t": translator,
        "app_name": settings.app_name,
        "current_user": current_user,
        "flash_message": flash_message,
    }


def add_flash_message(request: Request, message: str, category: str = "info") -> None:
    if hasattr(request, "session"):
        request.session["flash_message"] = {"text": message, "category": category}


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
