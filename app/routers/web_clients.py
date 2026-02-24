from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import add_flash_message, get_current_lang, get_db, template_context, templates
from app.i18n import make_t
from app.models.client import Client
from app.models.project import Project
from app.web_utils import clean_str, parse_checkbox, safe_commit
from app.services.form_utils import get_str

router = APIRouter(prefix="/clients", tags=["clients"])


def _parse_client_form(form_data: dict) -> dict:
    segment = (clean_str(form_data.get("client_segment")) or "B2C").upper()
    if segment not in {"B2C", "BRF", "B2B"}:
        segment = "B2C"

    return {
        "name": clean_str(get_str(form_data, "name")) or "",
        "contact_person": clean_str(get_str(form_data, "contact_person")),
        "phone": clean_str(get_str(form_data, "phone")),
        "email": clean_str(get_str(form_data, "email")),
        "address": clean_str(get_str(form_data, "address")),
        "comment": clean_str(get_str(form_data, "comment")),
        "is_private_person": parse_checkbox(form_data.get("is_private_person")),
        "is_rot_eligible": parse_checkbox(form_data.get("is_rot_eligible")),
        "client_segment": segment,
    }


def _apply_client_data(client: Client, data: dict) -> None:
    client.name = data["name"]
    client.contact_person = data["contact_person"]
    client.phone = data["phone"]
    client.email = data["email"]
    client.address = data["address"]
    client.comment = data["comment"]
    client.is_private_person = data["is_private_person"]
    client.is_rot_eligible = data["is_rot_eligible"]
    client.client_segment = data["client_segment"]


async def _save_client(
    request: Request,
    db: Session,
    lang: str,
    client_id: int | None,
    form_action: str,
):
    translator = make_t(lang)
    form_data = await request.form()
    data = _parse_client_form(form_data)

    resolved_client_id = client_id
    if resolved_client_id is None:
        raw_id = form_data.get("id")
        try:
            resolved_client_id = int(raw_id) if raw_id else None
        except (TypeError, ValueError):
            resolved_client_id = None

    client: Client | None = None
    if resolved_client_id is not None:
        client = db.get(Client, resolved_client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
    else:
        client = Client()

    if not data["name"]:
        add_flash_message(request, translator("clients.validation.name_required"), "error")
        context = template_context(request, lang)
        placeholder = SimpleNamespace(**{**data, "id": resolved_client_id})
        context.update({"client": placeholder, "form_action": form_action})
        return templates.TemplateResponse(request, "clients/form.html", context, status_code=400)

    _apply_client_data(client, data)
    db.add(client)
    if not safe_commit(db, request, message="save_client"):
        add_flash_message(request, translator("common.save_error_retry"), "error")
        context = template_context(request, lang)
        placeholder = SimpleNamespace(**{**data, "id": resolved_client_id})
        context.update({"client": placeholder, "form_action": form_action})
        return templates.TemplateResponse(request, "clients/form.html", context, status_code=400)
    db.refresh(client)

    add_flash_message(request, translator("clients.save.success"), "success")
    return RedirectResponse(url=f"/clients/{client.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/")
async def list_clients(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    clients = db.query(Client).all()
    context = template_context(request, lang)
    context["clients"] = clients
    return templates.TemplateResponse(request, "clients/list.html", context)


@router.get("/new")
async def new_client_form(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    context = template_context(request, lang)
    context.update({"client": None, "form_action": "/clients/save"})
    return templates.TemplateResponse(request, "clients/form.html", context)


@router.post("/new")
async def create_client(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    return await _save_client(
        request=request,
        db=db,
        lang=lang,
        client_id=None,
        form_action="/clients/new",
    )


@router.post("/save")
async def save_client(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    return await _save_client(
        request=request,
        db=db,
        lang=lang,
        client_id=None,
        form_action="/clients/save",
    )


@router.get("/{client_id}")
async def client_detail(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    projects = db.query(Project).filter(Project.client_id == client_id).all()
    context = template_context(request, lang)
    context.update({"client": client, "projects": projects})
    return templates.TemplateResponse(request, "clients/detail.html", context)


@router.get("/{client_id}/edit")
async def edit_client_form(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    context = template_context(request, lang)
    context.update({"client": client, "form_action": f"/clients/{client_id}/edit"})
    return templates.TemplateResponse(request, "clients/form.html", context)


@router.post("/{client_id}/edit")
async def update_client(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    return await _save_client(
        request=request,
        db=db,
        lang=lang,
        client_id=client_id,
        form_action=f"/clients/{client_id}/edit",
    )


@router.post("/{client_id}/delete")
async def delete_client(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    translator = make_t(lang)
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    project_count = db.query(Project).filter(Project.client_id == client_id).count()
    if project_count:
        add_flash_message(request, translator("clients.delete.blocked"), "error")
        return RedirectResponse(
            url=f"/clients/{client_id}", status_code=status.HTTP_303_SEE_OTHER
        )

    db.delete(client)
    if not safe_commit(db, request, message="delete_client"):
        add_flash_message(request, translator("common.delete_error_retry"), "error")
        return RedirectResponse(
            url=f"/clients/{client_id}", status_code=status.HTTP_303_SEE_OTHER
        )
    add_flash_message(request, translator("clients.delete.success"), "success")
    return RedirectResponse(url="/clients/", status_code=status.HTTP_303_SEE_OTHER)
