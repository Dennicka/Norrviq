from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import get_settings
from .db import Base, SessionLocal, engine
from .dependencies import get_current_lang
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
    web_materials,
    web_rooms,
    web_worktypes,
    web_workers,
)
from .security import require_auth
from .services.bootstrap import (
    ensure_default_cost_categories,
    ensure_default_legal_notes,
    ensure_default_worktypes,
)

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie_name,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

Base.metadata.create_all(bind=engine)


@app.on_event("startup")
def startup_event():
    db = SessionLocal()
    try:
        get_or_create_settings(db)
        ensure_default_cost_categories(db)
        ensure_default_legal_notes(db)
        ensure_default_worktypes(db)
    finally:
        db.close()


@app.middleware("http")
async def add_lang_to_request(request: Request, call_next):
    lang = await get_current_lang(request)
    request.state.lang = lang
    response = await call_next(request)
    return response


app.include_router(web_root.router)
app.include_router(web_auth.router)
app.include_router(web_clients.router, dependencies=[Depends(require_auth)])
app.include_router(web_worktypes.router, dependencies=[Depends(require_auth)])
app.include_router(web_projects.router, dependencies=[Depends(require_auth)])
app.include_router(web_settings.router, dependencies=[Depends(require_auth)])
app.include_router(web_costs.router, dependencies=[Depends(require_auth)])
app.include_router(web_legal.router, dependencies=[Depends(require_auth)])
app.include_router(web_materials.router, dependencies=[Depends(require_auth)])
app.include_router(web_rooms.router, dependencies=[Depends(require_auth)])
app.include_router(web_workers.router, dependencies=[Depends(require_auth)])
app.include_router(web_stats.router, dependencies=[Depends(require_auth)])
app.include_router(web_analytics.router, dependencies=[Depends(require_auth)])
app.include_router(web_help.router, dependencies=[Depends(require_auth)])
