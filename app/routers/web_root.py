from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from fastapi.responses import RedirectResponse

from ..config import get_settings
from ..services.setup_status import get_blocking_setup_checks
from ..dependencies import get_current_lang, get_db, template_context, templates

router = APIRouter()
settings = get_settings()


@router.get("/")
async def root(request: Request, lang: str = Depends(get_current_lang), db: Session = Depends(get_db)):
    if request.session.get("user_email") and get_blocking_setup_checks(db):
        return RedirectResponse(url="/onboarding", status_code=302)
    context = template_context(request, lang)
    return templates.TemplateResponse(request, "index.html", context)


@router.get("/lang/{lang_code}")
async def set_language(request: Request, lang_code: str):
    lang = lang_code if lang_code in ("ru", "sv", "en") else settings.default_lang
    next_url = request.query_params.get("next") or request.headers.get("referer") or "/"
    if not next_url.startswith("/"):
        next_url = "/"
    response = RedirectResponse(url=quote(next_url, safe="/:?&=%#"))
    response.set_cookie(key="lang", value=lang)
    return response
