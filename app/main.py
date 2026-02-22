import logging
from contextlib import asynccontextmanager

import itsdangerous
import multipart
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import models  # noqa: F401
from .config import get_settings
from .db import SessionLocal, ensure_schema_up_to_date
from .dependencies import enforce_csrf
from .models.settings import get_or_create_settings
from .models.company_profile import get_or_create_company_profile
from .observability import (
    REQUEST_ID_HEADER,
    configure_logging,
    ensure_lang,
    handle_readiness,
    http_exception_handler,
    log_access,
    metrics_registry,
    now_ms,
    record_metrics,
    resolve_request_id,
    unhandled_exception_handler,
    validation_exception_handler,
)
from .routers import (
    api_projects_autosave,
    api_buffer_rules,
    web_analytics,
    web_auth,
    web_buffer_rules,
    web_clients,
    web_documents,
    web_costs,
    web_help,
    web_invoices,
    web_legal,
    web_materials,
    web_payroll,
    web_projects,
    web_reports,
    web_root,
    web_rooms,
    web_settings,
    web_stats,
    web_workers,
    web_worktypes,
)
from .security import require_auth, require_role, validate_security_settings
from .services.bootstrap import (
    ensure_default_cost_categories,
    ensure_default_legal_notes,
    ensure_default_worktypes,
    ensure_default_speed_profiles,
)

settings = get_settings()
configure_logging(settings)
logger = logging.getLogger("uvicorn.error")



@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Using python-multipart from: %s", multipart.__file__)
    logger.info("Using itsdangerous from: %s", itsdangerous.__file__)
    ensure_schema_up_to_date()
    db = SessionLocal()
    try:
        get_or_create_settings(db)
        get_or_create_company_profile(db)
        ensure_default_cost_categories(db)
        ensure_default_legal_notes(db)
        ensure_default_worktypes(db)
        ensure_default_speed_profiles(db)
    finally:
        db.close()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

validate_security_settings()

resolved_secret = settings.secret_key

app.add_middleware(
    SessionMiddleware,
    secret_key=resolved_secret,
    session_cookie=settings.session_cookie_name,
    https_only=settings.cookie_secure,
    same_site=settings.cookie_same_site,
    max_age=settings.session_max_age_seconds,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    request.state.request_id = resolve_request_id(request)
    await ensure_lang(request)

    started = now_ms()
    try:
        response = await call_next(request)
    except Exception:
        latency_ms = now_ms() - started
        log_access(request, 500, latency_ms)
        record_metrics(request, 500, latency_ms)
        raise

    latency_ms = now_ms() - started
    response.headers[REQUEST_ID_HEADER] = request.state.request_id

    log_access(request, response.status_code, latency_ms)
    record_metrics(request, response.status_code, latency_ms)
    return response


@app.exception_handler(HTTPException)
async def app_http_exception_handler(request: Request, exc: HTTPException):
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def app_validation_exception_handler(request: Request, exc: RequestValidationError):
    return await validation_exception_handler(request, exc)


@app.exception_handler(Exception)
async def app_unhandled_exception_handler(request: Request, exc: Exception):
    return await unhandled_exception_handler(request, exc, settings)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(request: Request):
    is_ready, reason = await handle_readiness()
    if not is_ready:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": reason, "request_id": request.state.request_id},
            headers={REQUEST_ID_HEADER: request.state.request_id},
        )
    return {"status": "ready"}


@app.get("/metrics/basic")
async def basic_metrics():
    return metrics_registry.export()


csrf_dependency = Depends(enforce_csrf)

app.include_router(web_root.router, dependencies=[csrf_dependency])
app.include_router(api_buffer_rules.router, dependencies=[csrf_dependency, Depends(require_role("admin"))])
app.include_router(api_projects_autosave.router, dependencies=[csrf_dependency])
app.include_router(web_auth.router, dependencies=[csrf_dependency])
app.include_router(web_buffer_rules.router, dependencies=[csrf_dependency, Depends(require_role("admin"))])
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
app.include_router(web_documents.router, dependencies=[csrf_dependency, Depends(require_auth)])
