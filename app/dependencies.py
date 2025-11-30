from typing import Callable

from fastapi import Request
from fastapi.templating import Jinja2Templates

from .config import get_settings
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
    return {"request": request, "lang": lang, "t": translator, "app_name": settings.app_name}
