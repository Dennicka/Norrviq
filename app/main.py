from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import Base, engine
from .dependencies import get_current_lang
from .routers import web_clients, web_projects, web_root, web_worktypes

# Import models to ensure metadata is registered before table creation
from .models import client, cost, legal_note, project, settings as settings_model, worker, worktype  # noqa: F401

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

Base.metadata.create_all(bind=engine)


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
