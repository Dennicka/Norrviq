from decimal import Decimal

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, selectinload

from app.dependencies import add_flash_message, get_current_lang, get_db, template_context, templates
from app.models.client import Client
from app.models.company_profile import get_or_create_company_profile
from app.models.cost import CostCategory, ProjectCostItem
from app.models.legal_note import LegalNote
from app.models.material import Material
from app.models.project import Project, ProjectWorkItem, ProjectWorkerAssignment
from app.models.room import Room
from app.models.worker import Worker
from app.models.worktype import WorkType
from app.models.settings import get_or_create_settings
from app.services.estimates import calculate_project_totals, recalculate_project_work_items
from app.services.finance import calculate_project_financials, compute_project_finance
from app.security import require_auth
from app.i18n import make_t

router = APIRouter(prefix="/projects", tags=["projects"])


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@router.get("/")
async def list_projects(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    projects = db.query(Project).options(selectinload(Project.client)).all()
    context = template_context(request, lang)
    context["projects"] = projects
    return templates.TemplateResponse("projects/list.html", context)


@router.get("/new")
async def new_project_form(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    clients = db.query(Client).all()
    context = template_context(request, lang)
    context.update({"clients": clients, "project": None})
    return templates.TemplateResponse("projects/form.html", context)


@router.post("/new")
async def create_project(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    form = await request.form()
    client_id = form.get("client_id")
    project = Project(
        name=form.get("name"),
        client_id=int(client_id) if client_id else None,
        address=form.get("address"),
        description=form.get("description"),
        use_rot=bool(form.get("use_rot")),
        status=form.get("status") or "draft",
        planned_start_date=_parse_date(form.get("planned_start_date")),
        planned_end_date=_parse_date(form.get("planned_end_date")),
        actual_start_date=_parse_date(form.get("actual_start_date")),
        actual_end_date=_parse_date(form.get("actual_end_date")),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return RedirectResponse(url=f"/projects/{project.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{project_id}")
async def project_detail(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = (
        db.query(Project)
        .options(
            selectinload(Project.client),
            selectinload(Project.rooms),
            selectinload(Project.work_items).selectinload(ProjectWorkItem.work_type),
            selectinload(Project.worker_assignments).selectinload(ProjectWorkerAssignment.worker),
            selectinload(Project.cost_items).selectinload(ProjectCostItem.category),
            selectinload(Project.invoices),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    worktypes = db.query(WorkType).filter(WorkType.is_active).all()
    cost_categories = db.query(CostCategory).all()
    workers = db.query(Worker).all()
    materials = db.query(Material).filter(Material.is_active).all()
    rooms = sorted(project.rooms, key=lambda room: room.name.lower() if room.name else "")
    settings = get_or_create_settings(db)
    finance_summary = compute_project_finance(db, project, settings=settings)
    recent_invoices = sorted(
        project.invoices, key=lambda inv: inv.issue_date or inv.created_at or date.min, reverse=True
    )[:2]
    context = template_context(request, lang)
    context.update(
        {
            "project": project,
            "worktypes": worktypes,
            "cost_categories": cost_categories,
            "workers": workers,
            "materials": materials,
            "rooms": rooms,
            "finance_summary": finance_summary,
            "recent_invoices": recent_invoices,
        }
    )
    return templates.TemplateResponse("projects/detail.html", context)


@router.get("/{project_id}/edit")
async def edit_project_form(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    clients = db.query(Client).all()
    context = template_context(request, lang)
    context.update({"clients": clients, "project": project})
    return templates.TemplateResponse("projects/form.html", context)


@router.post("/{project_id}/edit")
async def update_project(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    form = await request.form()
    client_id = form.get("client_id")
    project.name = form.get("name")
    project.client_id = int(client_id) if client_id else None
    project.address = form.get("address")
    project.description = form.get("description")
    project.use_rot = bool(form.get("use_rot"))
    project.status = form.get("status") or project.status
    project.planned_start_date = _parse_date(form.get("planned_start_date"))
    project.planned_end_date = _parse_date(form.get("planned_end_date"))
    project.actual_start_date = _parse_date(form.get("actual_start_date"))
    project.actual_end_date = _parse_date(form.get("actual_end_date"))

    db.add(project)
    db.commit()

    return RedirectResponse(url=f"/projects/{project.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/delete")
async def delete_project(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = (
        db.query(Project)
        .options(
            selectinload(Project.work_items),
            selectinload(Project.worker_assignments),
            selectinload(Project.cost_items),
            selectinload(Project.rooms),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    translator = make_t(lang)
    has_dependencies = any(
        [project.work_items, project.worker_assignments, project.cost_items, project.rooms]
    )
    if has_dependencies:
        add_flash_message(request, translator("projects.delete.blocked"), "error")
        return RedirectResponse(
            url=f"/projects/{project.id}", status_code=status.HTTP_303_SEE_OTHER
        )

    db.delete(project)
    db.commit()
    add_flash_message(request, translator("projects.delete.success"), "success")
    return RedirectResponse(url="/projects/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{project_id}/offer", response_class=HTMLResponse)
def project_offer(
    project_id: int,
    request: Request,
    lang: str = Query("sv"),
    db: Session = Depends(get_db),
    current_user: str = Depends(require_auth),
):
    """
    Показывает чистый оферт-документ для клиента.
    """

    if lang not in ("ru", "sv"):
        lang = "sv"

    project = (
        db.query(Project)
        .options(
            selectinload(Project.client),
            selectinload(Project.work_items).selectinload(ProjectWorkItem.work_type),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    recalculate_project_work_items(db, project)
    calculate_project_totals(db, project)

    legal_notes = {
        note.code: note
        for note in db.query(LegalNote)
        .filter(LegalNote.code.in_(["ROT_BASICS", "MOMS_BASICS"]))
        .all()
    }

    context = template_context(request, lang)
    company_profile = get_or_create_company_profile(db)
    context.update(
        {
            "project": project,
            "client": project.client,
            "work_items": project.work_items,
            "offer_date": project.created_at.date() if project.created_at else date.today(),
            "legal_notes": legal_notes,
            "company_profile": company_profile,
            "offer_number": getattr(project, "offer_number", None),
        }
    )

    return templates.TemplateResponse("projects/offer.html", context)


@router.post("/{project_id}/add-work-item")
async def add_work_item(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    form = await request.form()
    work_type_id = form.get("work_type_id")
    work_type = db.get(WorkType, int(work_type_id)) if work_type_id else None
    if not work_type:
        raise HTTPException(status_code=400, detail="Work type required")

    room_id = form.get("room_id")
    room = db.get(Room, int(room_id)) if room_id else None
    if room and room.project_id != project.id:
        raise HTTPException(status_code=400, detail="Room is not part of project")

    item = ProjectWorkItem(
        project_id=project.id,
        work_type_id=work_type.id,
        room_id=room.id if room else None,
        quantity=Decimal(form.get("quantity") or "0"),
        difficulty_factor=Decimal(form.get("difficulty_factor") or "1"),
        comment=form.get("comment"),
    )
    db.add(item)
    db.commit()

    return RedirectResponse(url=f"/projects/{project.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{project_id}/items/{item_id}/edit")
async def edit_work_item_form(
    project_id: int,
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    item = (
        db.query(ProjectWorkItem)
        .options(selectinload(ProjectWorkItem.work_type), selectinload(ProjectWorkItem.project))
        .filter(ProjectWorkItem.id == item_id, ProjectWorkItem.project_id == project_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")

    project = item.project
    rooms = sorted(project.rooms, key=lambda room: room.name.lower() if room.name else "")
    worktypes = db.query(WorkType).filter(WorkType.is_active).all()

    context = template_context(request, lang)
    context.update({"project": project, "item": item, "rooms": rooms, "worktypes": worktypes})
    return templates.TemplateResponse("projects/work_item_form.html", context)


@router.post("/{project_id}/items/{item_id}/edit")
async def update_work_item(
    project_id: int,
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    translator = make_t(lang)
    item = (
        db.query(ProjectWorkItem)
        .options(
            selectinload(ProjectWorkItem.project).selectinload(Project.rooms),
            selectinload(ProjectWorkItem.work_type),
        )
        .filter(ProjectWorkItem.id == item_id, ProjectWorkItem.project_id == project_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")

    form = await request.form()
    room_id = form.get("room_id")
    room = db.get(Room, int(room_id)) if room_id else None
    if room and room.project_id != project_id:
        raise HTTPException(status_code=400, detail="Room is not part of project")

    work_type_id = form.get("work_type_id")
    work_type = db.get(WorkType, int(work_type_id)) if work_type_id else None
    if not work_type or not work_type.is_active:
        raise HTTPException(status_code=400, detail="Work type required")

    item.room = room
    item.work_type = work_type
    item.quantity = Decimal(form.get("quantity") or "0")
    item.difficulty_factor = Decimal(form.get("difficulty_factor") or "1")
    item.comment = form.get("comment")

    db.add(item)
    recalculate_project_work_items(db, item.project)
    calculate_project_totals(db, item.project)
    add_flash_message(request, translator("projects.work_items.updated"), "success")

    return RedirectResponse(
        url=f"/projects/{item.project_id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/{project_id}/items/{item_id}/delete")
async def delete_work_item(
    project_id: int,
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    translator = make_t(lang)
    item = (
        db.query(ProjectWorkItem)
        .filter(ProjectWorkItem.id == item_id, ProjectWorkItem.project_id == project_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")

    db.delete(item)
    db.commit()

    project = (
        db.query(Project)
        .options(selectinload(Project.work_items).selectinload(ProjectWorkItem.work_type))
        .filter(Project.id == project_id)
        .first()
    )
    if project:
        recalculate_project_work_items(db, project)
        calculate_project_totals(db, project)

    add_flash_message(request, translator("projects.work_items.deleted"), "success")
    return RedirectResponse(url=f"/projects/{project_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/recalculate")
async def recalc_project(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = (
        db.query(Project)
        .options(selectinload(Project.work_items).selectinload(ProjectWorkItem.work_type), selectinload(Project.client))
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    recalculate_project_work_items(db, project)
    calculate_project_totals(db, project)

    return RedirectResponse(url=f"/projects/{project.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/recalculate-finance")
async def recalculate_finance(project_id: int, db: Session = Depends(get_db)):
    project = (
        db.query(Project)
        .options(
            selectinload(Project.work_items).selectinload(ProjectWorkItem.work_type),
            selectinload(Project.client),
            selectinload(Project.worker_assignments).selectinload(ProjectWorkerAssignment.worker),
            selectinload(Project.cost_items).selectinload(ProjectCostItem.category),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    recalculate_project_work_items(db, project)
    calculate_project_totals(db, project)
    calculate_project_financials(db, project)

    return RedirectResponse(url=f"/projects/{project.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/add-cost-item")
async def add_cost_item(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    form = await request.form()
    category_id = form.get("cost_category_id")
    if not category_id:
        raise HTTPException(status_code=400, detail="Category required")
    material_id = form.get("material_id")
    material = db.get(Material, int(material_id)) if material_id else None
    cost_item = ProjectCostItem(
        project_id=project.id,
        cost_category_id=int(category_id),
        title=form.get("title") or (material.name_ru if material else None),
        amount=Decimal(form.get("amount") or (material.default_price_per_unit if material else "0")),
        comment=form.get("comment"),
        material=material,
    )
    db.add(cost_item)
    db.commit()

    calculate_project_financials(db, project)

    return RedirectResponse(url=f"/projects/{project.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/add-worker-assignment")
async def add_worker_assignment(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    form = await request.form()
    worker_id = form.get("worker_id")
    if not worker_id:
        raise HTTPException(status_code=400, detail="Worker required")

    assignment = ProjectWorkerAssignment(
        project_id=project.id,
        worker_id=int(worker_id),
        planned_hours=Decimal(form.get("planned_hours") or "0"),
        actual_hours=Decimal(form.get("actual_hours") or "0"),
    )
    db.add(assignment)
    db.commit()

    calculate_project_financials(db, project)

    return RedirectResponse(url=f"/projects/{project.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{project_id}/costs/{cost_id}/edit")
async def edit_cost_item_form(
    project_id: int,
    cost_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    cost_item = db.get(ProjectCostItem, cost_id)
    if not cost_item or cost_item.project_id != project.id:
        raise HTTPException(status_code=404, detail="Cost item not found")

    cost_categories = db.query(CostCategory).all()
    materials = db.query(Material).filter(Material.is_active).all()
    context = template_context(request, lang)
    context.update(
        {
            "project": project,
            "cost_item": cost_item,
            "cost_categories": cost_categories,
            "materials": materials,
        }
    )
    return templates.TemplateResponse("projects/cost_item_form.html", context)


@router.post("/{project_id}/costs/{cost_id}/save")
async def save_cost_item(
    project_id: int,
    cost_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    cost_item = db.get(ProjectCostItem, cost_id)
    if not cost_item or cost_item.project_id != project.id:
        raise HTTPException(status_code=404, detail="Cost item not found")

    form = await request.form()
    category_id = form.get("cost_category_id")
    if not category_id:
        raise HTTPException(status_code=400, detail="Category required")

    material_id = form.get("material_id") or None
    material = db.get(Material, int(material_id)) if material_id else None

    cost_item.cost_category_id = int(category_id)
    cost_item.material = material
    cost_item.title = form.get("title") or (material.name_ru if material else cost_item.title)
    cost_item.amount = Decimal(form.get("amount") or "0")
    cost_item.comment = form.get("comment")

    db.add(cost_item)
    db.commit()

    calculate_project_financials(db, project)

    translator = make_t(lang)
    add_flash_message(request, translator("projects.cost_items.updated"), "success")

    return RedirectResponse(url=f"/projects/{project.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/costs/{cost_id}/delete")
async def delete_cost_item(
    project_id: int,
    cost_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    cost_item = db.get(ProjectCostItem, cost_id)
    if not cost_item or cost_item.project_id != project.id:
        raise HTTPException(status_code=404, detail="Cost item not found")

    db.delete(cost_item)
    db.commit()

    calculate_project_financials(db, project)

    translator = make_t(lang)
    add_flash_message(request, translator("projects.cost_items.deleted"), "success")

    return RedirectResponse(url=f"/projects/{project.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{project_id}/hours/{assignment_id}/edit")
async def edit_assignment_form(
    project_id: int,
    assignment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    assignment = db.get(ProjectWorkerAssignment, assignment_id)
    if not assignment or assignment.project_id != project.id:
        raise HTTPException(status_code=404, detail="Assignment not found")

    workers = db.query(Worker).all()
    context = template_context(request, lang)
    context.update({"project": project, "assignment": assignment, "workers": workers})
    return templates.TemplateResponse("projects/worker_assignment_form.html", context)


@router.post("/{project_id}/hours/{assignment_id}/save")
async def save_assignment(
    project_id: int,
    assignment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    assignment = db.get(ProjectWorkerAssignment, assignment_id)
    if not assignment or assignment.project_id != project.id:
        raise HTTPException(status_code=404, detail="Assignment not found")

    form = await request.form()
    worker_id = form.get("worker_id")
    if not worker_id:
        raise HTTPException(status_code=400, detail="Worker required")

    assignment.worker_id = int(worker_id)
    assignment.planned_hours = Decimal(form.get("planned_hours") or "0")
    assignment.actual_hours = Decimal(form.get("actual_hours") or "0")

    db.add(assignment)
    db.commit()

    calculate_project_financials(db, project)

    translator = make_t(lang)
    add_flash_message(request, translator("projects.worker_assignments.updated"), "success")

    return RedirectResponse(url=f"/projects/{project.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/hours/{assignment_id}/delete")
async def delete_assignment(
    project_id: int,
    assignment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    assignment = db.get(ProjectWorkerAssignment, assignment_id)
    if not assignment or assignment.project_id != project.id:
        raise HTTPException(status_code=404, detail="Assignment not found")

    db.delete(assignment)
    db.commit()

    calculate_project_financials(db, project)

    translator = make_t(lang)
    add_flash_message(request, translator("projects.worker_assignments.deleted"), "success")

    return RedirectResponse(url=f"/projects/{project.id}", status_code=status.HTTP_303_SEE_OTHER)
