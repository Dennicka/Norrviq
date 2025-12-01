from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.dependencies import get_current_lang, template_context, templates

router = APIRouter(prefix="/help", tags=["help"])


@router.get("/", response_class=HTMLResponse)
def help_page(request: Request, lang: str = Depends(get_current_lang)):
    context = template_context(request, lang)
    return templates.TemplateResponse("help/index.html", context)
