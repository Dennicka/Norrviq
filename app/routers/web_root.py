from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session
from fastapi.responses import RedirectResponse

from ..config import get_settings
from ..services.setup_status import get_blocking_setup_checks
from ..dependencies import add_flash_message, get_current_lang, get_db, template_context, templates
from ..models.project import Project

router = APIRouter()
settings = get_settings()
WIZARD_STEPS = {"object", "rooms", "works", "pricing", "materials", "review", "documents"}


def _normalize_wizard_step(step: str | None) -> str:
    candidate = (step or "").strip().lower()
    if candidate in WIZARD_STEPS:
        return candidate
    return "rooms"


def _wizard_redirect_target(request: Request, db: Session, normalized_step: str) -> str:
    project_id = request.query_params.get("project_id")
    if project_id and project_id.isdigit():
        selected_project_id = int(project_id)
    else:
        latest_project = db.query(Project).order_by(Project.id.desc()).first()
        if not latest_project:
            add_flash_message(request, "Создайте проект, чтобы запустить мастер", "warning")
            return "/projects/new"
        selected_project_id = latest_project.id
    return f"/projects/{selected_project_id}/wizard?step={normalized_step}"


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


@router.get("/wizard")
async def wizard_entrypoint(
    request: Request,
    step: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    normalized_step = _normalize_wizard_step(step)
    redirect_target = _wizard_redirect_target(request, db, normalized_step)
    return RedirectResponse(url=redirect_target, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/wizard/{step}")
async def wizard_step_entrypoint(
    step: str,
    request: Request,
    db: Session = Depends(get_db),
):
    normalized_step = _normalize_wizard_step(step)
    redirect_target = _wizard_redirect_target(request, db, normalized_step)
    return RedirectResponse(url=redirect_target, status_code=status.HTTP_303_SEE_OTHER)
