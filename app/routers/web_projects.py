from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, selectinload

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.client import Client
from app.models.project import Project, ProjectWorkItem
from app.models.worktype import WorkType
from app.services.estimates import calculate_project_totals, recalculate_project_work_items

router = APIRouter(prefix="/projects", tags=["projects"])


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
    context.update({"clients": clients})
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
        use_rot=bool(form.get("use_rot")),
        status=form.get("status") or "draft",
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
            selectinload(Project.work_items).selectinload(ProjectWorkItem.work_type),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    worktypes = db.query(WorkType).all()
    context = template_context(request, lang)
    context.update({"project": project, "worktypes": worktypes})
    return templates.TemplateResponse("projects/detail.html", context)


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

    item = ProjectWorkItem(
        project_id=project.id,
        work_type_id=work_type.id,
        quantity=Decimal(form.get("quantity") or "0"),
        difficulty_factor=Decimal(form.get("difficulty_factor") or "1"),
        comment=form.get("comment"),
    )
    db.add(item)
    db.commit()

    return RedirectResponse(url=f"/projects/{project.id}", status_code=status.HTTP_303_SEE_OTHER)


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
