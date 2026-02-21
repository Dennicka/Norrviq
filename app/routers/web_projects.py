import json
from decimal import Decimal, InvalidOperation

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session, selectinload

from app.dependencies import add_flash_message, get_current_lang, get_db, template_context, templates
from app.models.client import Client
from app.models.company_profile import get_or_create_company_profile
from app.models.cost import CostCategory, ProjectCostItem
from app.models.legal_note import LegalNote
from app.models.material import Material
from app.models.audit_event import AuditEvent
from app.models.project import Project, ProjectWorkItem, ProjectWorkerAssignment
from app.models.room import Room
from app.models.worker import Worker
from app.models.worktype import WorkType
from app.models.settings import get_or_create_settings
from app.services.estimates import calculate_project_totals, recalculate_project_work_items
from app.services.finance import calculate_project_financials, compute_project_finance
from app.services.terms_templates import DOC_TYPE_OFFER, resolve_terms_template
from app.services.pricing import (
    LOW_MARGIN_WARN_PCT,
    WARNING_LOW_MARGIN,
    WARNING_MISSING_BASELINE,
    WARNING_MISSING_ITEMS,
    WARNING_MISSING_UNITS_M2,
    WARNING_MISSING_UNITS_ROOMS,
    WARNING_NEGATIVE_MARGIN,
    WARNING_INVALID_TARGET_MARGIN,
    DesiredInput,
    PricingValidationError,
    compute_conversions,
    compute_pricing_scenarios,
    get_or_create_project_pricing,
    select_pricing_mode,
    update_project_pricing,
)
from app.security import OPERATOR_ROLE, ADMIN_ROLE, get_current_user_email, get_current_user_role, require_auth
from app.i18n import make_t

router = APIRouter(prefix="/projects", tags=["projects"])

CRITICAL_WARNING_CODES = {
    WARNING_MISSING_UNITS_M2,
    WARNING_MISSING_UNITS_ROOMS,
    WARNING_MISSING_ITEMS,
}


def _normalize_for_display(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    try:
        if not value.is_finite():
            return None
    except InvalidOperation:
        return None
    quantized = value.quantize(Decimal("0.01"))
    if quantized == Decimal("-0.00"):
        return Decimal("0.00")
    return quantized


def _format_money(value: Decimal | None) -> str:
    normalized = _normalize_for_display(value)
    return f"{normalized:.2f}" if normalized is not None else "—"


def _format_hourly(value: Decimal | None) -> str:
    normalized = _normalize_for_display(value)
    return f"{normalized:.2f}" if normalized is not None else "—"


def _format_margin_pct(value: Decimal | None) -> str:
    normalized = _normalize_for_display(value)
    if normalized is None:
        return "—"
    return f"{normalized.quantize(Decimal('0.1')):.1f}%"


def _warning_text(code: str) -> str:
    if code == WARNING_MISSING_UNITS_M2:
        return "Нет площади (0 м²), режим за м² недоступен"
    if code == WARNING_MISSING_UNITS_ROOMS:
        return "Нет комнат (0), режим за комнату недоступен"
    if code == WARNING_MISSING_ITEMS:
        return "Нет работ (0 позиций), piecework недоступен"
    if code == WARNING_MISSING_BASELINE:
        return "Нет базовых трудозатрат (0 ч), effective hourly не рассчитывается"
    if code == WARNING_NEGATIVE_MARGIN:
        return "Отрицательная маржа: цена ниже полной себестоимости"
    if code == WARNING_LOW_MARGIN:
        return f"Низкая маржа: ниже {LOW_MARGIN_WARN_PCT}%"
    if code == WARNING_INVALID_TARGET_MARGIN:
        return "Невозможно: target margin должен быть меньше 100%"
    return code


def _scenario_view_model(scenario):
    warning_codes = list(dict.fromkeys(scenario.warnings))
    critical_codes = [code for code in warning_codes if code in CRITICAL_WARNING_CODES]
    return {
        "raw": scenario,
        "mode": scenario.mode,
        "price_ex_vat_display": _format_money(scenario.price_ex_vat),
        "vat_amount_display": _format_money(scenario.vat_amount),
        "price_inc_vat_display": _format_money(scenario.price_inc_vat),
        "effective_hourly_display": _format_hourly(scenario.effective_hourly_sell_rate),
        "profit_display": _format_money(scenario.profit),
        "margin_pct_display": _format_margin_pct(scenario.margin_pct),
        "warning_codes": warning_codes,
        "warnings": [{"code": code, "text": _warning_text(code)} for code in warning_codes],
        "critical_warnings": critical_codes,
        "not_applicable": scenario.invalid and bool(critical_codes),
    }


def _conversion_view_model(result):
    if result is None:
        return None
    warning_codes = list(dict.fromkeys(result.warnings))
    return {
        "raw": result,
        "fixed_total_display": _format_money(result.implied_fixed_total_price),
        "effective_hourly_display": _format_hourly(result.effective_hourly_ex_vat),
        "rate_per_m2_display": _format_money(result.implied_rate_per_m2),
        "rate_per_room_display": _format_money(result.implied_rate_per_room),
        "rate_per_piece_display": _format_money(result.implied_rate_per_piece),
        "profit_display": _format_money(result.profit),
        "margin_pct_display": _format_margin_pct(result.margin_pct),
        "warnings": [{"code": code, "text": _warning_text(code)} for code in warning_codes],
    }


def _parse_conversion_decimal(value: str | None):
    if value in (None, ""):
        return None
    try:
        decimal_value = Decimal(value)
    except (InvalidOperation, TypeError):
        return None
    if decimal_value <= 0:
        return None
    return decimal_value.quantize(Decimal("0.01"))


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
    get_or_create_project_pricing(db, project.id)
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
    if project.offer_status == "issued":
        terms_title = project.offer_terms_snapshot_title or ""
        terms_body = project.offer_terms_snapshot_body or ""
    else:
        terms_template = resolve_terms_template(
            db,
            profile=company_profile,
            client=project.client,
            doc_type=DOC_TYPE_OFFER,
            lang=lang,
        )
        terms_title = terms_template.title
        terms_body = terms_template.body_text
    context.update(
        {
            "project": project,
            "client": project.client,
            "work_items": project.work_items,
            "offer_date": project.created_at.date() if project.created_at else date.today(),
            "legal_notes": legal_notes,
            "company_profile": company_profile,
            "offer_number": project.offer_number,
            "offer_status": project.offer_status,
            "terms_title": terms_title,
            "terms_body": terms_body,
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


@router.get("/{project_id}/pricing")
async def project_pricing_screen(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    pricing = get_or_create_project_pricing(db, project_id)
    baseline, scenarios = compute_pricing_scenarios(db, project_id)
    scenario_views = [_scenario_view_model(scenario) for scenario in scenarios]
    db.add(
        AuditEvent(
            event_type="pricing_scenarios_viewed",
            user_id=get_current_user_email(request),
            entity_type="project",
            entity_id=project_id,
            details=json.dumps({"project_id": project_id}, ensure_ascii=False),
        )
    )
    db.commit()
    is_readonly = get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE}
    wants_json = "application/json" in request.headers.get("accept", "")
    if wants_json:
        return JSONResponse(
            {
                "id": pricing.id,
                "project_id": pricing.project_id,
                "mode": pricing.mode,
                "hourly_rate_override": str(pricing.hourly_rate_override) if pricing.hourly_rate_override is not None else None,
                "fixed_total_price": str(pricing.fixed_total_price) if pricing.fixed_total_price is not None else None,
                "rate_per_m2": str(pricing.rate_per_m2) if pricing.rate_per_m2 is not None else None,
                "rate_per_room": str(pricing.rate_per_room) if pricing.rate_per_room is not None else None,
                "rate_per_piece": str(pricing.rate_per_piece) if pricing.rate_per_piece is not None else None,
                "target_margin_pct": str(pricing.target_margin_pct) if pricing.target_margin_pct is not None else None,
                "include_materials": pricing.include_materials,
                "include_travel_setup_buffers": pricing.include_travel_setup_buffers,
                "currency": pricing.currency,
                "baseline": {
                    "labor_hours_total": str(baseline.labor_hours_total),
                    "labor_cost_internal": str(baseline.labor_cost_internal),
                    "materials_cost_internal": str(baseline.materials_cost_internal),
                    "travel_setup_cost_internal": str(baseline.travel_setup_cost_internal),
                    "overhead_cost_internal": str(baseline.overhead_cost_internal),
                    "internal_total_cost": str(baseline.internal_total_cost),
                    "total_m2": str(baseline.total_m2),
                    "rooms_count": baseline.rooms_count,
                    "items_count": baseline.items_count,
                },
                "scenarios": [
                    {
                        "mode": sc.mode,
                        "price_ex_vat": str(sc.price_ex_vat),
                        "vat_amount": str(sc.vat_amount),
                        "price_inc_vat": str(sc.price_inc_vat),
                        "effective_hourly_sell_rate": str(sc.effective_hourly_sell_rate) if sc.effective_hourly_sell_rate is not None else None,
                        "profit": str(sc.profit),
                        "margin_pct": str(sc.margin_pct) if sc.margin_pct is not None else None,
                        "warnings": sc.warnings,
                        "invalid": sc.invalid,
                        "details_lines": sc.details_lines,
                    }
                    for sc in scenarios
                ],
            }
        )

    context = template_context(request, lang)
    effective_by_mode = {scenario.mode: _format_hourly(scenario.effective_hourly_sell_rate) for scenario in scenarios}
    context.update(
        {
            "project": project,
            "pricing": pricing,
            "form_data": {
                "mode": pricing.mode,
                "hourly_rate_override": pricing.hourly_rate_override,
                "fixed_total_price": pricing.fixed_total_price,
                "rate_per_m2": pricing.rate_per_m2,
                "rate_per_room": pricing.rate_per_room,
                "rate_per_piece": pricing.rate_per_piece,
                "target_margin_pct": pricing.target_margin_pct,
                "include_materials": pricing.include_materials,
                "include_travel_setup_buffers": pricing.include_travel_setup_buffers,
                "currency": pricing.currency,
            },
            "converter_input": {},
            "conversion_result": None,
            "errors": {},
            "is_readonly": is_readonly,
            "baseline": baseline,
            "scenarios": scenario_views,
            "effective_by_mode": effective_by_mode,
        }
    )
    return templates.TemplateResponse("projects/pricing.html", context)


@router.post("/{project_id}/pricing")
async def update_project_pricing_screen(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    pricing = get_or_create_project_pricing(db, project_id)
    form = await request.form()
    payload = dict(form)
    intent = payload.get("intent") or "save_pricing"
    role = get_current_user_role(request)

    if intent in {"save_pricing", "select_mode", "apply_conversion"} and role not in {ADMIN_ROLE, OPERATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Insufficient role")

    converter_input = {
        "desired_effective_hourly_ex_vat": payload.get("desired_effective_hourly_ex_vat") or "",
        "desired_margin_pct": payload.get("desired_margin_pct") or "",
    }

    if intent == "calculate_conversion":
        desired = DesiredInput(
            desired_effective_hourly_ex_vat=_parse_conversion_decimal(payload.get("desired_effective_hourly_ex_vat")),
            desired_margin_pct=_parse_conversion_decimal(payload.get("desired_margin_pct")),
        )
        if desired.desired_effective_hourly_ex_vat is None and desired.desired_margin_pct is None:
            for field_name in ("rate_per_m2", "rate_per_room", "rate_per_piece", "fixed_total_price"):
                value = _parse_conversion_decimal(payload.get(field_name))
                if value is not None:
                    setattr(desired, field_name, value)
                    break
        conversion_result = compute_conversions(db, project_id, desired)
        db.add(
            AuditEvent(
                event_type="pricing_conversion_calculated",
                user_id=get_current_user_email(request),
                entity_type="project",
                entity_id=project_id,
                details=json.dumps(
                    {
                        "project_id": project_id,
                        "desired_effective_hourly_ex_vat": converter_input["desired_effective_hourly_ex_vat"] or None,
                        "desired_margin_pct": converter_input["desired_margin_pct"] or None,
                        "warnings": conversion_result.warnings,
                    },
                    ensure_ascii=False,
                ),
            )
        )
        db.commit()

        baseline, scenarios = compute_pricing_scenarios(db, project_id)
        scenario_views = [_scenario_view_model(scenario) for scenario in scenarios]
        context = template_context(request, lang)
        context.update(
            {
                "project": project,
                "pricing": pricing,
                "form_data": {
                    "mode": pricing.mode,
                    "hourly_rate_override": pricing.hourly_rate_override,
                    "fixed_total_price": pricing.fixed_total_price,
                    "rate_per_m2": pricing.rate_per_m2,
                    "rate_per_room": pricing.rate_per_room,
                    "rate_per_piece": pricing.rate_per_piece,
                    "target_margin_pct": pricing.target_margin_pct,
                    "include_materials": pricing.include_materials,
                    "include_travel_setup_buffers": pricing.include_travel_setup_buffers,
                    "currency": pricing.currency,
                },
                "converter_input": converter_input,
                "conversion_result": _conversion_view_model(conversion_result),
                "errors": {},
                "is_readonly": role not in {ADMIN_ROLE, OPERATOR_ROLE},
                "baseline": baseline,
                "scenarios": scenario_views,
                "effective_by_mode": {scenario.mode: _format_hourly(scenario.effective_hourly_sell_rate) for scenario in scenarios},
            }
        )
        return templates.TemplateResponse("projects/pricing.html", context)

    if intent == "apply_conversion":
        apply_mode = (payload.get("apply_mode") or "").upper()
        apply_value = _parse_conversion_decimal(payload.get("apply_value"))
        mode_to_field = {
            "FIXED_TOTAL": "fixed_total_price",
            "PER_M2": "rate_per_m2",
            "PER_ROOM": "rate_per_room",
            "PIECEWORK": "rate_per_piece",
        }
        field_name = mode_to_field.get(apply_mode)
        if field_name is None or apply_value is None:
            raise HTTPException(status_code=400, detail="Invalid conversion apply payload")
        setattr(pricing, field_name, apply_value)
        db.add(pricing)
        db.add(
            AuditEvent(
                event_type="pricing_conversion_applied",
                user_id=get_current_user_email(request),
                entity_type="project",
                entity_id=project_id,
                details=json.dumps({"project_id": project_id, "mode": apply_mode, "value": str(apply_value)}, ensure_ascii=False),
            )
        )
        db.commit()
        add_flash_message(request, "Conversion applied", "success")
        return RedirectResponse(url=f"/projects/{project_id}/pricing", status_code=status.HTTP_303_SEE_OTHER)

    try:
        if intent == "select_mode":
            select_pricing_mode(
                db,
                pricing=pricing,
                mode=payload.get("selected_mode") or "",
                user_id=get_current_user_email(request),
            )
        else:
            update_project_pricing(
                db,
                pricing=pricing,
                payload=payload,
                user_id=get_current_user_email(request),
            )
    except PricingValidationError as exc:
        baseline, scenarios = compute_pricing_scenarios(db, project_id)
        scenario_views = [_scenario_view_model(scenario) for scenario in scenarios]
        context = template_context(request, lang)
        context.update(
            {
                "project": project,
                "pricing": pricing,
                "form_data": payload,
                "converter_input": converter_input,
                "conversion_result": None,
                "errors": exc.errors,
                "is_readonly": False,
                "baseline": baseline,
                "scenarios": scenario_views,
                "effective_by_mode": {scenario.mode: _format_hourly(scenario.effective_hourly_sell_rate) for scenario in scenarios},
            }
        )
        return templates.TemplateResponse("projects/pricing.html", context, status_code=400)

    return RedirectResponse(
        url=f"/projects/{project_id}/pricing", status_code=status.HTTP_303_SEE_OTHER
    )
