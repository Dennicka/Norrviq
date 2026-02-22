from typing import Callable, Optional
import logging

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal
from .i18n import make_t
from .help.render import help_icon
from .security import ensure_csrf_token, validate_csrf_token
from .maintenance import is_enabled

settings = get_settings()
templates = Jinja2Templates(directory="app/templates")


def csrf_input(request: Request) -> Markup:
    token = ensure_csrf_token(request)
    return Markup(f'<input type="hidden" name="csrf_token" value="{escape(token)}">')


templates.env.globals["csrf_input"] = csrf_input
templates.env.globals["help_icon"] = help_icon



logger = logging.getLogger("uvicorn.error")


async def enforce_csrf(request: Request) -> None:
    safe_methods = {"GET", "HEAD", "OPTIONS"}
    exempt_paths = ("/static/", "/api/health")

    if any(request.url.path.startswith(path) for path in exempt_paths):
        return

    if request.method in safe_methods:
        ensure_csrf_token(request)
        return

    csrf_token = request.headers.get("X-CSRF-Token")
    if not csrf_token and "application/json" not in request.headers.get("content-type", ""):
        form = await request.form()
        csrf_token = form.get("csrf_token")

    if validate_csrf_token(request, csrf_token):
        return

    request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id")
    logger.warning(
        "csrf_reject path=%s method=%s user_id=%s request_id=%s",
        request.url.path,
        request.method,
        request.session.get("user_email"),
        request_id,
    )
    raise HTTPException(status_code=403, detail="Invalid or missing CSRF token")


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
        "csrf_token": ensure_csrf_token(request),
        "maintenance_mode": is_enabled(),
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
