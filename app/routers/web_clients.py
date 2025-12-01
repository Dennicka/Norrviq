from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import add_flash_message, get_current_lang, get_db, template_context, templates
from app.i18n import make_t
from app.models.client import Client
from app.models.project import Project

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("/")
async def list_clients(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    clients = db.query(Client).all()
    context = template_context(request, lang)
    context["clients"] = clients
    return templates.TemplateResponse("clients/list.html", context)


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
    return templates.TemplateResponse("clients/detail.html", context)


@router.get("/new")
async def new_client_form(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    context = template_context(request, lang)
    context["client"] = None
    return templates.TemplateResponse("clients/form.html", context)


@router.post("/new")
async def create_client(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    form = await request.form()
    client = Client(
        name=form.get("name"),
        contact_person=form.get("contact_person"),
        phone=form.get("phone"),
        email=form.get("email"),
        address=form.get("address"),
        comment=form.get("comment"),
        is_private_person=bool(form.get("is_private_person")),
        is_rot_eligible=bool(form.get("is_rot_eligible")),
    )
    db.add(client)
    db.commit()
    return RedirectResponse(url="/clients/", status_code=status.HTTP_303_SEE_OTHER)


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
    context["client"] = client
    return templates.TemplateResponse("clients/form.html", context)


@router.post("/{client_id}/edit")
async def update_client(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    form = await request.form()
    client.name = form.get("name")
    client.contact_person = form.get("contact_person")
    client.phone = form.get("phone")
    client.email = form.get("email")
    client.address = form.get("address")
    client.comment = form.get("comment")
    client.is_private_person = bool(form.get("is_private_person"))
    client.is_rot_eligible = bool(form.get("is_rot_eligible"))

    db.add(client)
    db.commit()

    return RedirectResponse(url="/clients/", status_code=status.HTTP_303_SEE_OTHER)


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
    db.commit()
    add_flash_message(request, translator("clients.delete.success"), "success")
    return RedirectResponse(url="/clients/", status_code=status.HTTP_303_SEE_OTHER)
