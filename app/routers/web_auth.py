from urllib.parse import parse_qs
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.status import HTTP_302_FOUND

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.security import get_current_user_email, log_auth_event
from app.services.auth import authenticate_user

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, lang: str = Depends(get_current_lang), next: str = "/"):
    current_user = get_current_user_email(request)
    if current_user:
        return RedirectResponse(url="/", status_code=HTTP_302_FOUND)

    context = template_context(request, lang)
    context["next_path"] = next
    context["invalid_credentials"] = False
    return templates.TemplateResponse(request, "auth/login.html", context)


@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    form = await request.body()
    data = dict((key, values[0]) for key, values in parse_qs(form.decode()).items())
    email = data.get("email") or data.get("username", "")
    password = data.get("password", "")
    next_path = data.get("next", "/")

    user = authenticate_user(db, email=email, password=password)
    if user:
        request.session.clear()
        request.session["sid"] = str(uuid4())
        request.session["user_email"] = user.email
        request.session["user_role"] = user.role
        log_auth_event("login_success", user_email=user.email, role=user.role)
        return RedirectResponse(url=next_path or "/", status_code=HTTP_302_FOUND)

    log_auth_event("login_failed", user_email=email.strip().lower())
    context = template_context(request, lang)
    context["next_path"] = next_path
    context["invalid_credentials"] = True
    return templates.TemplateResponse(request, "auth/login.html", context)


@router.get("/logout")
async def logout(request: Request):
    user_email = request.session.get("user_email")
    request.session.clear()
    if user_email:
        log_auth_event("logout", user_email=user_email)
    return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)
