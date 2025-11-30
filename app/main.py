from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .dependencies import get_current_lang
from .routers import web_root

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.middleware("http")
async def add_lang_to_request(request: Request, call_next):
    lang = await get_current_lang(request)
    request.state.lang = lang
    response = await call_next(request)
    return response


app.include_router(web_root.router)
