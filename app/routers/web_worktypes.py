from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.project import ProjectWorkItem
from app.models.worktype import WORKTYPE_UNITS, WorkType
from app.web_utils import FormValidationError, parse_checkbox, parse_decimal_field, parse_int_field, safe_commit


async def _extract_form_data(request: Request) -> dict:
    return dict(await request.form())

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
    context = template_context(request, lang)
    context["worktype_units"] = WORKTYPE_UNITS
    try:
        minutes = parse_int_field(form.get("minutes_per_unit"), field_name="minutes_per_unit", min_value=0)
        hours = parse_decimal_field(form.get("hours_per_unit"), field_name="hours_per_unit", min_value=Decimal("0"))
        base_difficulty_factor = parse_decimal_field(
            form.get("base_difficulty_factor") or "1",
            field_name="base_difficulty_factor",
            min_value=Decimal("0"),
        )
    except FormValidationError as exc:
        context.update({"worktype": WorkType(**{k: v for k, v in form.items() if k in WorkType.__table__.columns.keys()}), "error_message": str(exc)})
        return templates.TemplateResponse(request, "worktypes/form.html", context, status_code=400)

    worktype = WorkType(
        code=form.get("code"),
        category=form.get("category"),
        unit=form.get("unit"),
        name_ru=form.get("name_ru"),
        name_sv=form.get("name_sv"),
        description_ru=form.get("description_ru"),
        description_sv=form.get("description_sv"),
        hours_per_unit=hours,
        base_difficulty_factor=base_difficulty_factor,
        is_active=parse_checkbox(form.get("is_active")),
    )
    worktype.set_minutes_per_unit(minutes)
    db.add(worktype)
    if not safe_commit(db, request, message="create_worktype"):
        context.update({"worktype": worktype, "error_message": "Не удалось сохранить вид работ. Попробуйте снова."})
        return templates.TemplateResponse(request, "worktypes/form.html", context, status_code=400)
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
    context = template_context(request, lang)
    context["worktype_units"] = WORKTYPE_UNITS
    try:
        minutes = parse_int_field(form.get("minutes_per_unit"), field_name="minutes_per_unit", min_value=0)
        hours = parse_decimal_field(form.get("hours_per_unit"), field_name="hours_per_unit", min_value=Decimal("0"))
        base_difficulty_factor = parse_decimal_field(
            form.get("base_difficulty_factor") or "1",
            field_name="base_difficulty_factor",
            min_value=Decimal("0"),
        )
    except FormValidationError as exc:
        context.update({"worktype": worktype, "error_message": str(exc)})
        return templates.TemplateResponse(request, "worktypes/form.html", context, status_code=400)
    worktype.code = form.get("code")
    worktype.category = form.get("category")
    worktype.unit = form.get("unit")
    worktype.name_ru = form.get("name_ru")
    worktype.name_sv = form.get("name_sv")
    worktype.description_ru = form.get("description_ru")
    worktype.description_sv = form.get("description_sv")
    worktype.hours_per_unit = hours
    worktype.set_minutes_per_unit(minutes)
    worktype.base_difficulty_factor = base_difficulty_factor
    worktype.is_active = parse_checkbox(form.get("is_active"))

    db.add(worktype)
    if not safe_commit(db, request, message="update_worktype"):
        context.update({"worktype": worktype, "error_message": "Не удалось обновить вид работ. Попробуйте снова."})
        return templates.TemplateResponse(request, "worktypes/form.html", context, status_code=400)

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
    if not safe_commit(db, request, message="delete_worktype"):
        context = template_context(request, lang)
        context.update({"worktypes": db.query(WorkType).all(), "worktype_units": WORKTYPE_UNITS, "error_message": "worktypes.error.cannot_delete_in_use"})
        return templates.TemplateResponse(request, "worktypes/list.html", context, status_code=400)
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
