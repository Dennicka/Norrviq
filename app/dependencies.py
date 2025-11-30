from typing import Callable

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
    current_user = request.session.get("user") if hasattr(request, "session") else None
    return {
        "request": request,
        "lang": lang,
        "t": translator,
        "app_name": settings.app_name,
        "current_user": current_user,
    }


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
