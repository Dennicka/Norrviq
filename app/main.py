from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import Base, SessionLocal, engine
from .dependencies import get_current_lang
from .models import client, cost, legal_note, project, settings as settings_model, worker, worktype  # noqa: F401
from .models.settings import get_or_create_settings
from .routers import (
    web_clients,
    web_costs,
    web_legal,
    web_projects,
    web_root,
    web_settings,
    web_stats,
    web_worktypes,
    web_workers,
)
from .services.bootstrap import ensure_default_cost_categories, ensure_default_legal_notes

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

Base.metadata.create_all(bind=engine)


@app.on_event("startup")
def startup_event():
    db = SessionLocal()
    try:
        get_or_create_settings(db)
        ensure_default_cost_categories(db)
        ensure_default_legal_notes(db)
    finally:
        db.close()


@app.middleware("http")
async def add_lang_to_request(request: Request, call_next):
    lang = await get_current_lang(request)
    request.state.lang = lang
    response = await call_next(request)
    return response


app.include_router(web_root.router)
app.include_router(web_clients.router)
app.include_router(web_worktypes.router)
app.include_router(web_projects.router)
app.include_router(web_settings.router)
app.include_router(web_costs.router)
app.include_router(web_legal.router)
app.include_router(web_workers.router)
app.include_router(web_stats.router)
