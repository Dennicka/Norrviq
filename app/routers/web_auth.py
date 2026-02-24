from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.status import HTTP_302_FOUND

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.audit import log_event
from app.security import get_current_user_email
from app.services.auth import authenticate_user
from app.web_utils import clean_str, safe_commit
from app.services.form_utils import get_str

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
    form = await request.form()
    email = clean_str(get_str(form, "email") or get_str(form, "username")) or ""
    password = get_str(form, "password")
    next_path = clean_str(get_str(form, "next")) or "/"

    user = authenticate_user(db, email=email, password=password)
    if user:
        request.session.clear()
        request.session["sid"] = str(uuid4())
        request.session["user_email"] = user.email
        request.session["user_role"] = user.role
        log_event(db, request, "login_success", entity_type="SYSTEM", severity="SECURITY", metadata={"user_email": user.email, "role": user.role})
        if not safe_commit(db, request, message="login_success_audit"):
            context = template_context(request, lang)
            context["next_path"] = next_path
            context["invalid_credentials"] = True
            return templates.TemplateResponse(request, "auth/login.html", context, status_code=400)
        return RedirectResponse(url=next_path, status_code=HTTP_302_FOUND)

    log_event(db, request, "login_failed", entity_type="SYSTEM", severity="SECURITY", metadata={"user_email": email.strip().lower()})
    safe_commit(db, request, message="login_failed_audit")
    context = template_context(request, lang)
    context["next_path"] = next_path
    context["invalid_credentials"] = True
    return templates.TemplateResponse(request, "auth/login.html", context)


@router.get("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    user_email = request.session.get("user_email")
    request.session.clear()
    if user_email:
        log_event(db, request, "logout", entity_type="SYSTEM", severity="SECURITY", metadata={"user_email": user_email})
        safe_commit(db, request, message="logout_audit")
    return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)
