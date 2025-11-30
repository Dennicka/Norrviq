from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_302_FOUND

from app.dependencies import get_current_lang, template_context, templates
from app.security import authenticate_user, get_current_username

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, lang: str = Depends(get_current_lang), next: str = "/"):
    current_user = get_current_username(request)
    if current_user:
        return RedirectResponse(url="/", status_code=HTTP_302_FOUND)

    context = template_context(request, lang)
    context["next_path"] = next
    context["invalid_credentials"] = False
    return templates.TemplateResponse("auth/login.html", context)


@router.post("/login")
async def login(request: Request, lang: str = Depends(get_current_lang)):
    form = await request.body()
    data = dict(
        (key, values[0]) for key, values in parse_qs(form.decode()).items()
    )
    username = data.get("username", "")
    password = data.get("password", "")
    next_path = data.get("next", "/")

    if authenticate_user(username, password):
        request.session["user"] = username
        return RedirectResponse(url=next_path or "/", status_code=HTTP_302_FOUND)

    context = template_context(request, lang)
    context["next_path"] = next_path
    context["invalid_credentials"] = True
    return templates.TemplateResponse("auth/login.html", context)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)
