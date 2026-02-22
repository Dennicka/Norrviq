from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from ..config import get_settings
from ..dependencies import get_current_lang, template_context, templates

router = APIRouter()
settings = get_settings()


@router.get("/")
async def root(request: Request, lang: str = Depends(get_current_lang)):
    context = template_context(request, lang)
    return templates.TemplateResponse(request, "index.html", context)


@router.get("/lang/{lang_code}")
async def set_language(lang_code: str):
    lang = lang_code if lang_code in ("ru", "sv") else settings.default_lang
    response = RedirectResponse(url="/")
    response.set_cookie(key="lang", value=lang)
    return response
