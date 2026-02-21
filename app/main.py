import logging

import itsdangerous
import multipart
from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import models  # noqa: F401
from .config import get_settings
from .db import SessionLocal, ensure_schema_up_to_date
from .dependencies import enforce_csrf, get_current_lang
from .models.settings import get_or_create_settings
from .routers import (
    web_auth,
    web_analytics,
    web_clients,
    web_costs,
    web_legal,
    web_help,
    web_projects,
    web_root,
    web_settings,
    web_stats,
    web_payroll,
    web_materials,
    web_reports,
    web_rooms,
    web_invoices,
    web_worktypes,
    web_workers,
)
from .security import require_auth, require_role, validate_security_settings
from .services.auth import ensure_admin_user
from .services.bootstrap import (
    ensure_default_cost_categories,
    ensure_default_legal_notes,
    ensure_default_worktypes,
)

settings = get_settings()
logger = logging.getLogger("uvicorn.error")

app = FastAPI(title=settings.app_name)

validate_security_settings()

resolved_secret = settings.app_secret_key or "dev-insecure-secret-key"

app.add_middleware(
    SessionMiddleware,
    secret_key=resolved_secret,
    session_cookie=settings.session_cookie_name,
    https_only=not settings.allow_dev_defaults,
    same_site="lax",
    max_age=settings.session_max_age_seconds,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
def startup_event():
    logger.info("Using python-multipart from: %s", multipart.__file__)
    logger.info("Using itsdangerous from: %s", itsdangerous.__file__)
    ensure_schema_up_to_date()
    db = SessionLocal()
    try:
        get_or_create_settings(db)
        ensure_default_cost_categories(db)
        ensure_default_legal_notes(db)
        ensure_default_worktypes(db)
        ensure_admin_user(db)
    finally:
        db.close()


@app.middleware("http")
async def add_lang_to_request(request: Request, call_next):
    lang = await get_current_lang(request)
    request.state.lang = lang
    response = await call_next(request)
    return response


csrf_dependency = Depends(enforce_csrf)

app.include_router(web_root.router, dependencies=[csrf_dependency])
app.include_router(web_auth.router, dependencies=[csrf_dependency])
app.include_router(web_clients.router, dependencies=[csrf_dependency, Depends(require_auth)])
app.include_router(web_worktypes.router, dependencies=[csrf_dependency, Depends(require_auth)])
app.include_router(web_projects.router, dependencies=[csrf_dependency, Depends(require_auth)])
app.include_router(web_settings.router, dependencies=[csrf_dependency, Depends(require_role("admin"))])
app.include_router(web_costs.router, dependencies=[csrf_dependency, Depends(require_auth)])
app.include_router(web_legal.router, dependencies=[csrf_dependency, Depends(require_auth)])
app.include_router(web_materials.router, dependencies=[csrf_dependency, Depends(require_auth)])
app.include_router(web_invoices.router, dependencies=[csrf_dependency, Depends(require_auth)])
app.include_router(web_reports.router, dependencies=[csrf_dependency, Depends(require_auth)])
app.include_router(web_rooms.router, dependencies=[csrf_dependency, Depends(require_auth)])
app.include_router(web_workers.router, dependencies=[csrf_dependency, Depends(require_auth)])
app.include_router(web_stats.router, dependencies=[csrf_dependency, Depends(require_auth)])
app.include_router(web_analytics.router, dependencies=[csrf_dependency, Depends(require_auth)])
app.include_router(web_payroll.router, dependencies=[csrf_dependency, Depends(require_auth)])
app.include_router(web_help.router, dependencies=[csrf_dependency, Depends(require_auth)])
