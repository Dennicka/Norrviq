from decimal import Decimal
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.project import ProjectWorkItem
from app.models.worktype import WORKTYPE_UNITS, WorkType


async def _extract_form_data(request: Request) -> dict:
    data: dict = {}
    try:
        form = await request.form()
        data = dict(form)
    except Exception:
        data = {}

    if not data:
        body = await request.body()
        if body:
            data = {key: values[0] for key, values in parse_qs(body.decode()).items()}
    return data

router = APIRouter(prefix="/worktypes", tags=["worktypes"])


@router.get("/")
async def list_worktypes(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    worktypes = db.query(WorkType).all()
    context = template_context(request, lang)
    context["worktypes"] = worktypes
    context["worktype_units"] = WORKTYPE_UNITS
    return templates.TemplateResponse(request, "worktypes/list.html", context)


@router.get("/new")
async def new_worktype_form(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    context = template_context(request, lang)
    context["worktype"] = None
    context["worktype_units"] = WORKTYPE_UNITS
    return templates.TemplateResponse(request, "worktypes/form.html", context)


@router.post("/new")
async def create_worktype(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    form = await _extract_form_data(request)
    minutes_raw = form.get("minutes_per_unit")
    hours_raw = form.get("hours_per_unit")
    minutes = int(minutes_raw) if minutes_raw not in (None, "") else None
    hours = Decimal(hours_raw) if hours_raw not in (None, "") else None

    worktype = WorkType(
        code=form.get("code"),
        category=form.get("category"),
        unit=form.get("unit"),
        name_ru=form.get("name_ru"),
        name_sv=form.get("name_sv"),
        description_ru=form.get("description_ru"),
        description_sv=form.get("description_sv"),
        hours_per_unit=hours,
        base_difficulty_factor=Decimal(form.get("base_difficulty_factor") or "1"),
        is_active=bool(form.get("is_active")),
    )
    worktype.set_minutes_per_unit(minutes)
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
    context["worktype_units"] = WORKTYPE_UNITS
    return templates.TemplateResponse(request, "worktypes/form.html", context)


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

    form = await _extract_form_data(request)
    minutes_raw = form.get("minutes_per_unit")
    hours_raw = form.get("hours_per_unit")
    minutes = int(minutes_raw) if minutes_raw not in (None, "") else None
    hours = Decimal(hours_raw) if hours_raw not in (None, "") else None
    worktype.code = form.get("code")
    worktype.category = form.get("category")
    worktype.unit = form.get("unit")
    worktype.name_ru = form.get("name_ru")
    worktype.name_sv = form.get("name_sv")
    worktype.description_ru = form.get("description_ru")
    worktype.description_sv = form.get("description_sv")
    worktype.hours_per_unit = hours
    worktype.set_minutes_per_unit(minutes)
    worktype.base_difficulty_factor = Decimal(form.get("base_difficulty_factor") or "1")
    worktype.is_active = bool(form.get("is_active"))

    db.add(worktype)
    db.commit()

    return RedirectResponse(url="/worktypes/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{worktype_id}/delete")
async def delete_worktype(
    worktype_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    worktype = db.get(WorkType, worktype_id)
    if not worktype:
        raise HTTPException(status_code=404, detail="WorkType not found")
    is_in_use = (
        db.query(ProjectWorkItem)
        .filter(ProjectWorkItem.work_type_id == worktype.id)
        .count()
        > 0
    )
    if is_in_use:
        context = template_context(request, lang)
        context.update(
            {
                "worktypes": db.query(WorkType).all(),
                "worktype_units": WORKTYPE_UNITS,
                "error_message": "worktypes.error.cannot_delete_in_use",
            }
        )
        return templates.TemplateResponse(request, "worktypes/list.html", context, status_code=400)

    db.delete(worktype)
    db.commit()
    return RedirectResponse(url="/worktypes/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{worktype_id}/copy")
async def copy_worktype_form(
    worktype_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    worktype = db.get(WorkType, worktype_id)
    if not worktype:
        raise HTTPException(status_code=404, detail="WorkType not found")

    copy_code = f"{worktype.code}_copy" if worktype.code else ""
    prefilled = WorkType(
        code=copy_code,
        category=worktype.category,
        unit=worktype.unit,
        name_ru=worktype.name_ru,
        name_sv=worktype.name_sv,
        description_ru=worktype.description_ru,
        description_sv=worktype.description_sv,
        hours_per_unit=worktype.hours_per_unit,
        base_difficulty_factor=worktype.base_difficulty_factor,
        is_active=True,
    )
    context = template_context(request, lang)
    context.update({"worktype": prefilled, "worktype_units": WORKTYPE_UNITS})
    return templates.TemplateResponse(request, "worktypes/form.html", context)


@router.post("/{worktype_id}/toggle-active")
async def toggle_worktype_active(worktype_id: int, db: Session = Depends(get_db)):
    worktype = db.get(WorkType, worktype_id)
    if not worktype:
        raise HTTPException(status_code=404, detail="WorkType not found")
    worktype.is_active = not worktype.is_active
    db.add(worktype)
    db.commit()
    return RedirectResponse(url="/worktypes/", status_code=status.HTTP_303_SEE_OTHER)
