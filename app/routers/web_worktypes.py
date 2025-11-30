from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.worktype import WorkType

router = APIRouter(prefix="/worktypes", tags=["worktypes"])


@router.get("/")
async def list_worktypes(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    worktypes = db.query(WorkType).all()
    context = template_context(request, lang)
    context["worktypes"] = worktypes
    return templates.TemplateResponse("worktypes/list.html", context)


@router.get("/new")
async def new_worktype_form(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    context = template_context(request, lang)
    context["worktype"] = None
    return templates.TemplateResponse("worktypes/form.html", context)


@router.post("/new")
async def create_worktype(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    form = await request.form()
    minutes = Decimal(form.get("minutes_per_unit") or "0")
    worktype = WorkType(
        code=form.get("code"),
        category=form.get("category"),
        unit=form.get("unit"),
        name_ru=form.get("name_ru"),
        name_sv=form.get("name_sv"),
        description_ru=form.get("description_ru"),
        description_sv=form.get("description_sv"),
        hours_per_unit=minutes / Decimal(60),
        base_difficulty_factor=Decimal(form.get("base_difficulty_factor") or "1"),
        is_active=bool(form.get("is_active")),
    )
    db.add(worktype)
    db.commit()
    return RedirectResponse(url="/worktypes/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{worktype_id}/edit")
async def edit_worktype_form(
    worktype_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    worktype = db.get(WorkType, worktype_id)
    if not worktype:
        raise HTTPException(status_code=404, detail="WorkType not found")

    context = template_context(request, lang)
    context["worktype"] = worktype
    return templates.TemplateResponse("worktypes/form.html", context)


@router.post("/{worktype_id}/edit")
async def update_worktype(
    worktype_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    worktype = db.get(WorkType, worktype_id)
    if not worktype:
        raise HTTPException(status_code=404, detail="WorkType not found")

    form = await request.form()
    minutes = Decimal(form.get("minutes_per_unit") or "0")
    worktype.code = form.get("code")
    worktype.category = form.get("category")
    worktype.unit = form.get("unit")
    worktype.name_ru = form.get("name_ru")
    worktype.name_sv = form.get("name_sv")
    worktype.description_ru = form.get("description_ru")
    worktype.description_sv = form.get("description_sv")
    worktype.hours_per_unit = minutes / Decimal(60)
    worktype.base_difficulty_factor = Decimal(form.get("base_difficulty_factor") or "1")
    worktype.is_active = bool(form.get("is_active"))

    db.add(worktype)
    db.commit()

    return RedirectResponse(url="/worktypes/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{worktype_id}/delete")
async def delete_worktype(worktype_id: int, db: Session = Depends(get_db)):
    worktype = db.get(WorkType, worktype_id)
    if not worktype:
        raise HTTPException(status_code=404, detail="WorkType not found")
    db.delete(worktype)
    db.commit()
    return RedirectResponse(url="/worktypes/", status_code=status.HTTP_303_SEE_OTHER)
