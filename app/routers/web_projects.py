import csv
import io
import json
from pathlib import Path
import logging
from decimal import Decimal, InvalidOperation

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session, selectinload

from app.dependencies import add_flash_message, get_current_lang, get_db, template_context, templates
from app.models.client import Client
from app.models.company_profile import get_or_create_company_profile
from app.models.cost import CostCategory, ProjectCostItem
from app.models.legal_note import LegalNote
from app.models.material import Material
from app.models.material_consumption_override import MaterialConsumptionOverride
from app.models.paint_system import PaintSystem
from app.models.invoice import Invoice
from app.models.terms_template import TermsTemplate
from app.models.audit_event import AuditEvent
from app.audit import log_event
from app.models.project import Project, ProjectWorkItem, ProjectWorkerAssignment
from app.models.project_takeoff_settings import M2_BASIS_CHOICES
from app.models.speed_profile import SpeedProfile
from app.models.pricing_policy import get_or_create_pricing_policy
from app.models.room import Room
from app.models.worker import Worker
from app.models.worktype import WorkType
from app.models.settings import get_or_create_settings
from app.services.estimates import (
    calculate_project_total_hours,
    calculate_project_totals,
    calculate_project_pricing_totals,
    recalculate_project_work_items,
    SCOPE_MODE_ROOM,
)
from app.services.offer_commercial import compute_offer_commercial, deserialize_offer_commercial, is_offer_snapshot_stale, serialize_offer_commercial
from app.services.commercial_snapshot import DOC_TYPE_OFFER as SNAP_OFFER, read_commercial_snapshot
from app.services.finance import calculate_project_financials, compute_project_finance
from app.services.terms_templates import DOC_TYPE_OFFER, resolve_terms_template
from app.services.invoice_documents import normalize_document_lang
from app.services.buffer_audit import log_buffer_audit
from app.services.quality import evaluate_project_quality
from app.services.completeness import compute_completeness
from app.services.geometry import aggregate_project_geometry
from app.services.project_estimator import build_project_estimate_summary
from app.services.project_pricing import build_project_pricing_summary
from app.services.workflow import build_project_workflow_state
from app.services.work_scope_apply import apply_work_item_to_scope
from app.services.estimator_workspace import build_estimator_workspace
from app.services.estimator_engine import recalculate_project_work_items as recalc_estimator_project
from app.services.work_packages import apply_package_to_project, list_active_packages, package_description, package_icon, package_label
from app.services.work_packages_apply import apply_package, list_applied_package_codes, remove_package
from app.services.pricing import (
    LOW_MARGIN_WARN_PCT,
    WARNING_LOW_MARGIN,
    WARNING_MISSING_BASELINE,
    WARNING_MISSING_ITEMS,
    WARNING_MISSING_UNITS_M2,
    WARNING_MISSING_PERIMETER_HEIGHT,
    WARNING_MISSING_UNITS_ROOMS,
    WARNING_NEGATIVE_MARGIN,
    WARNING_INVALID_TARGET_MARGIN,
    DesiredInput,
    PricingValidationError,
    compute_conversions,
    compute_pricing_scenarios,
    compute_project_baseline,
    get_or_create_project_pricing,
    get_or_create_project_buffer_settings,
    get_or_create_project_execution_profile,
    select_pricing_mode,
    update_project_pricing,
    evaluate_floor,
)
from app.services.pricing_sanity import NO_VALID_PRICING_SCENARIO
from app.services.takeoff import compute_project_areas, get_or_create_project_takeoff_settings, validate_m2_basis
from app.services.materials_bom import (
    apply_bom_to_invoice_material_lines,
    apply_bom_to_project_cost_items,
    compute_project_bom,
    get_or_create_project_material_settings,
    get_or_create_project_paint_settings,
)
from app.services.materials_consumption import calculate_material_needs_for_project
from app.services.material_norms import build_project_material_bom
from app.services.material_costing import cost_project_materials
from app.services.pdf_renderer import invoice_pdf_capability, render_pdf_from_html_with_engine
from app.services.request_cache import RequestCache, get_request_cache
from app.services.invoice_lines import MERGE_REPLACE_ALL, generate_invoice_lines_from_project
from app.services.correctness_lock import validate_estimate_invariants, validate_offer_invariants, validate_pricing_invariants, validate_invoice_invariants
from app.services.shopping_list import (
    apply_shopping_list_to_invoice_material_lines,
    apply_shopping_list_to_project_cost_items,
    compute_project_shopping_list,
    get_or_create_procurement_settings,
)
from app.models.project_procurement_settings import RoundingMode
from app.services.material_actuals import (
    build_quick_add_idempotency_key,
    compute_materials_plan_vs_actual,
    create_material_purchase,
    export_plan_vs_actual_csv,
    export_plan_vs_actual_pdf,
    export_purchases_csv,
    upsert_actual_entry,
)
from app.models.supplier import Supplier
from app.models.user import User
from app.observability import REQUEST_ID_HEADER
from app.web_utils import clean_str, parse_checkbox, parse_int_field, safe_commit
from app.security import OPERATOR_ROLE, ADMIN_ROLE, get_current_user_email, get_current_user_role, require_auth, require_role
from app.i18n import make_t

router = APIRouter(prefix="/projects", tags=["projects"])
logger = logging.getLogger("uvicorn.error")
MAX_IMPORT_FILE_BYTES = 5 * 1024 * 1024
IMPORT_SESSION_KEY = "csv_import_previews"
ROOMS_EXPORT_COLUMNS = ["room_id", "name", "floor_area_m2", "perimeter_m", "ceiling_height_m", "notes"]
WORK_ITEMS_EXPORT_COLUMNS = ["item_id", "room_id", "room_name", "work_type_code", "work_type_name", "quantity", "unit", "notes"]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PDF_STYLESHEET = PROJECT_ROOT / "app" / "static" / "css" / "pdf_document.css"

CRITICAL_WARNING_CODES = {
    WARNING_MISSING_UNITS_M2,
    WARNING_MISSING_UNITS_ROOMS,
    WARNING_MISSING_ITEMS,
}




def _parse_decimal_override(request: Request, value: str | None, key: str, t):
    try:
        parsed = Decimal(str(value or "")).quantize(Decimal("0.0001"))
    except Exception:
        add_flash_message(request, t(key), "error")
        return None
    return parsed


def _allowed_surface_kind(value: str) -> bool:
    return value in {"walls", "ceiling", "floor", "combined", "pieces"}


def _allowed_unit_basis(value: str) -> bool:
    return value in {"m2", "piece", "room"}

def _parse_purchase_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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


def _find_preset_work_type(worktypes: list[WorkType], preset: str) -> WorkType | None:
    keys = {
        "floor_protection": ["protect", "защит", "skydd", "floor"],
        "ceiling_paint": ["ceiling", "потол", "tak", "paint"],
        "wall_paint": ["wall", "стен", "vägg", "paint"],
        "wall_putty": ["putty", "шпат", "spack"],
        "sanding": ["sand", "шлиф", "slip"],
        "primer": ["primer", "грунт"],
        "baseboard_paint": ["plint", "плинт", "sockel", "paint"],
    }
    markers = keys.get(preset, [])
    for wt in worktypes:
        haystack = " ".join([str(wt.code or ""), str(wt.category or ""), str(wt.name_ru or ""), str(wt.name_sv or "")]).lower()
        if all(any(m in haystack for m in [marker]) for marker in markers[:1]) and any(m in haystack for m in markers):
            return wt
    return None


def _warning_text(code: str) -> str:
    if code == WARNING_MISSING_UNITS_M2:
        return "Нет площади (0 м²), режим за м² недоступен"
    if code == WARNING_MISSING_PERIMETER_HEIGHT:
        return "Для выбранной базы m² не хватает perimeter/height в комнатах"
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


M2_BASIS_LABELS_RU = {
    "FLOOR_AREA": "Площадь пола",
    "WALL_AREA": "Площадь стен",
    "CEILING_AREA": "Площадь потолка",
    "PAINTABLE_TOTAL": "Покрашиваемая площадь (стены + потолок)",
}


def _scenario_view_model(scenario, floor_result=None):
    warning_codes = list(dict.fromkeys(scenario.warnings))
    sanity_warns = [issue for issue in getattr(scenario, "sanity_issues", []) if issue.get("severity") == "WARN"]
    critical_codes = [code for code in warning_codes if code in CRITICAL_WARNING_CODES]
    floor_reasons = []
    if floor_result is not None:
        floor_reasons = [{"code": item.code, "text": item.text} for item in floor_result.reasons]
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
        "sanity_warnings": sanity_warns,
        "critical_warnings": critical_codes,
        "not_applicable": scenario.invalid and bool(critical_codes),
        "floor": floor_result,
        "floor_badge": "BELOW FLOOR" if floor_result and floor_result.is_below_floor else "OK",
        "floor_reasons": floor_reasons,
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


def _pick_best_pricing_mode(scenarios, metric: str = "profit") -> str | None:
    valid = [scenario for scenario in scenarios if not scenario.invalid and getattr(scenario, "is_valid", True)]
    if not valid:
        return None
    normalized_metric = (metric or "profit").strip().lower()
    if normalized_metric == "effective_hourly":
        ranked = sorted(
            valid,
            key=lambda scenario: scenario.effective_hourly_sell_rate if scenario.effective_hourly_sell_rate is not None else Decimal("-1"),
            reverse=True,
        )
        return ranked[0].mode if ranked else None
    ranked = sorted(valid, key=lambda scenario: scenario.profit, reverse=True)
    return ranked[0].mode if ranked else None


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


def _parse_local_decimal(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    cleaned = str(raw).strip().replace(" ", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, TypeError):
        return None


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_csv_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned == "":
        return None
    if "," in cleaned:
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None




def _parse_pricing_form(form) -> dict:
    mode_raw = (form.get("pricing_mode") or "hourly").lower()
    mode = "sqm" if mode_raw == "area" else mode_raw
    data = {"pricing_mode": mode, "hourly_rate_sek": None, "area_rate_sek": None, "fixed_price_sek": None}

    def _to_decimal(key: str):
        raw = form.get(key)
        if raw in (None, ""):
            return None
        return Decimal(str(raw))

    data["hourly_rate_sek"] = _to_decimal("hourly_rate_sek")
    data["area_rate_sek"] = _to_decimal("area_rate_sek")
    data["fixed_price_sek"] = _to_decimal("fixed_price_sek")


    return data


def _validate_pricing_form(pricing_data: dict, *, quantity: Decimal, has_area: bool) -> str | None:
    mode = pricing_data["pricing_mode"]
    if mode not in {"hourly", "sqm", "fixed"}:
        return "Invalid pricing mode"
    if mode == "fixed" and pricing_data["fixed_price_sek"] is None:
        return "Fixed mode requires fixed price"
    if mode == "hourly":
        if quantity <= 0:
            return "Hourly mode requires quantity/hours"
    if mode == "sqm":
        if pricing_data["area_rate_sek"] is None:
            return "SQM mode requires m² rate"
        if quantity <= 0 and not has_area:
            return "SQM mode requires area"
    return None

def _read_csv_rows(file_bytes: bytes) -> tuple[list[str], list[dict[str, str]]]:
    text = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=",")
    if not reader.fieldnames:
        return [], []
    return [h.strip() for h in reader.fieldnames], [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in reader]


def _audit_event(request: Request, db: Session, *, event_type: str, project_id: int, details: dict, severity: str = "INFO") -> None:
    log_event(
        db,
        request,
        event_type,
        entity_type="PROJECT",
        entity_id=project_id,
        severity=severity,
        metadata=details,
    )


def _get_import_previews(request: Request) -> dict:
    previews = request.session.get(IMPORT_SESSION_KEY)
    if not isinstance(previews, dict):
        previews = {}
        request.session[IMPORT_SESSION_KEY] = previews
    return previews


def build_project_context(db: Session, request: Request, project: Project, lang: str, **extra):
    context = template_context(request, lang)
    mode = ((extra.get("pricing") and extra.get("pricing").mode) or (project.pricing.mode if project.pricing else "HOURLY"))
    segment = (project.client.client_segment if project.client and project.client.client_segment else "ANY")
    completeness_report = compute_completeness(db, project.id, mode=mode, segment=segment, lang=lang)
    context.update({"project": project, "quality_report": evaluate_project_quality(db, project.id, lang=lang), "completeness_report": completeness_report})
    context.update(extra)
    return context


PROJECT_WORKSPACE_TABS = {
    "overview",
    "rooms",
    "scope",
    "materials",
    "buffers",
    "pricing",
    "documents",
    "audit",
}

WIZARD_STEPS = ["object", "rooms", "works", "pricing", "materials", "review", "documents"]
WIZARD_NEXT_STEP = {current: WIZARD_STEPS[index + 1] for index, current in enumerate(WIZARD_STEPS[:-1])}
WIZARD_PREV_STEP = {current: WIZARD_STEPS[index - 1] for index, current in enumerate(WIZARD_STEPS[1:], start=1)}

WIZARD_OBJECT_TYPES = ["house", "apartment", "office", "commercial"]
WIZARD_ROOM_TEMPLATES = {
    "apartment": {
        "studio": ["Hallway", "Bathroom", "Kitchen", "Living room"],
        "1br": ["Hallway", "Bathroom", "Kitchen", "Living room", "Bedroom 1"],
        "2br": ["Hallway", "Bathroom", "Kitchen", "Living room", "Bedroom 1", "Bedroom 2"],
        "3br": ["Hallway", "Bathroom", "Kitchen", "Living room", "Bedroom 1", "Bedroom 2", "Bedroom 3"],
    },
    "house": {
        "small": ["Hallway", "Kitchen", "Bathroom", "Living room", "Bedroom 1"],
        "medium": ["Hallway", "Kitchen", "Bathroom", "Living room", "Bedroom 1", "Bedroom 2"],
        "large": ["Hallway", "Kitchen", "Bathroom", "Living room", "Bedroom 1", "Bedroom 2", "Bedroom 3"],
    },
}


def _build_wizard_summary(db: Session, project_id: int, *, cache: RequestCache | None = None) -> dict:
    pricing = get_or_create_project_pricing(db, project_id)
    project = db.get(Project, project_id)
    pricing_totals = calculate_project_pricing_totals(project)
    geometry = aggregate_project_geometry(db, project_id, cache=cache)
    material_plan = cost_project_materials(db, project_id)
    return {
        "hours_total": calculate_project_total_hours(db, project_id),
        "sell_ex_vat": pricing_totals.total_price_sek,
        "materials_total": material_plan.total_ex_vat,
        "profit": pricing_totals.total_margin_sek,
        "margin_pct": pricing_totals.total_margin_pct,
        "pricing_mode": pricing.mode or "HOURLY",
        "floor_area_m2": geometry.total_floor_area_m2,
    }


def _resolve_wizard_step(raw_step: str | None) -> str | None:
    candidate = (raw_step or "").strip().lower()
    if candidate in WIZARD_STEPS:
        return candidate
    return None


def _resolve_project_tab(raw_tab: str | None) -> str:
    candidate = (raw_tab or "overview").strip().lower()
    return candidate if candidate in PROJECT_WORKSPACE_TABS else "overview"


def _project_redirect_with_tab(project_id: int, request: Request, fallback_tab: str = "overview") -> str:
    tab_value = request.query_params.get("tab")
    tab = _resolve_project_tab(tab_value or fallback_tab)
    return f"/projects/{project_id}?tab={tab}"


@router.get("/")
async def list_projects(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    projects = db.query(Project).options(selectinload(Project.client)).all()
    context = template_context(request, lang)
    context["projects"] = projects
    workflow_states = {}
    for project in projects:
        try:
            workflow_states[project.id] = build_project_workflow_state(db, project.id, lang=lang)
        except Exception:
            workflow_states[project.id] = {"workflow_status": "draft", "updated_at": None}
    context["workflow_states"] = workflow_states
    return templates.TemplateResponse(request, "projects/list.html", context)


@router.get("/new")
async def new_project_form(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    clients = db.query(Client).all()
    context = template_context(request, lang)
    context.update({"clients": clients, "project": None})
    return templates.TemplateResponse(request, "projects/form.html", context)


@router.post("/new")
async def create_project(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    form = await request.form()
    client_id = form.get("client_id")
    project = Project(
        name=clean_str(form.get("name")),
        client_id=parse_int_field(client_id, field_name="client_id") if client_id else None,
        address=clean_str(form.get("address")),
        description=clean_str(form.get("description")),
        use_rot=parse_checkbox(form.get("use_rot")),
        status=clean_str(form.get("status")) or "draft",
        planned_start_date=_parse_date(form.get("planned_start_date")),
        planned_end_date=_parse_date(form.get("planned_end_date")),
        actual_start_date=_parse_date(form.get("actual_start_date")),
        actual_end_date=_parse_date(form.get("actual_end_date")),
    )
    db.add(project)
    if not safe_commit(db, request, message="create_project"):
        add_flash_message(request, make_t(lang)("common.save_error_retry"), "error")
        clients = db.query(Client).all()
        context = template_context(request, lang)
        context.update({"clients": clients, "project": project})
        return templates.TemplateResponse(request, "projects/form.html", context, status_code=400)
    db.refresh(project)
    get_or_create_project_pricing(db, project.id)
    return RedirectResponse(url=f"/projects/{project.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{project_id}")
async def project_detail(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    room_ids: list[int] = Query(default=[]),
    tab: str = Query("overview"),
    cache: RequestCache = Depends(get_request_cache),
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
    baseline = compute_project_baseline(db, project.id, include_materials=True, include_travel_setup_buffers=True, cache=cache)
    recent_invoices = sorted(
        project.invoices, key=lambda inv: inv.issue_date or inv.created_at or date.min, reverse=True
    )[:2]
    geometry_summary = aggregate_project_geometry(db, project.id, cache=cache)
    pricing = get_or_create_project_pricing(db, project.id)
    estimator_mode_map = {"HOURLY": "hourly", "PER_M2": "sqm", "FIXED_TOTAL": "fixed"}
    estimator_summary = build_project_estimate_summary(
        project=project,
        room_ids=room_ids,
        pricing_mode=estimator_mode_map.get((pricing.mode or "HOURLY").upper(), "hourly"),
        hourly_rate=Decimal(str(pricing.hourly_rate_override or settings.hourly_rate_company or 0)),
        sqm_rate=Decimal(str(pricing.rate_per_m2 or 0)),
        fixed_price=Decimal(str(pricing.fixed_total_price or 0)),
        vat_rate_percent=Decimal(str(settings.moms_percent or 0)),
    )
    material_cost_report = cost_project_materials(db, project.id)
    if estimator_summary.totals:
        estimator_summary.totals.subtotal_materials = material_cost_report.total_ex_vat
        estimator_summary.totals.subtotal = estimator_summary.totals.subtotal_labour + material_cost_report.total_ex_vat
        estimator_summary.totals.vat_amount = estimator_summary.totals.subtotal * Decimal(str(settings.moms_percent or 0)) / Decimal("100")
        estimator_summary.totals.total_inc_vat = estimator_summary.totals.subtotal + estimator_summary.totals.vat_amount
    material_rows, material_totals = calculate_material_needs_for_project(db, project.id)
    auto_bom = build_project_material_bom(project.id, db)
    pricing_summary = build_project_pricing_summary(project, db)
    active_tab = _resolve_project_tab(tab)
    company_profile = get_or_create_company_profile(db)
    selected_invoice = recent_invoices[0] if recent_invoices else None
    offer_lang = normalize_document_lang(project.offer_document_lang, fallback=normalize_document_lang(lang))
    invoice_lang = normalize_document_lang(
        selected_invoice.document_lang if selected_invoice else None,
        fallback=normalize_document_lang(lang),
    )
    doc_type = (request.query_params.get("doc_type") or "offer").strip().lower()
    if doc_type not in {"offer", "invoice"}:
        doc_type = "offer"
    selected_doc_lang = offer_lang if doc_type == "offer" else invoice_lang
    segment = (project.client.client_segment if project.client and project.client.client_segment else "B2C")
    terms_doc_type = DOC_TYPE_OFFER if doc_type == "offer" else "INVOICE"
    terms_template = resolve_terms_template(
        db,
        profile=company_profile,
        client=project.client,
        doc_type=terms_doc_type,
        lang=selected_doc_lang,
    )
    terms_templates = (
        db.query(TermsTemplate)
        .filter(TermsTemplate.doc_type == terms_doc_type, TermsTemplate.is_active.is_(True))
        .order_by(TermsTemplate.segment.asc(), TermsTemplate.lang.asc(), TermsTemplate.version.desc())
        .all()
    )
    company_missing_fields: list[str] = []
    required_company = {
        "company.legal_name": company_profile.legal_name,
        "company.org_number": company_profile.org_number,
        "company.address_line1": company_profile.address_line1,
        "company.postal_code": company_profile.postal_code,
        "company.city": company_profile.city,
        "company.email": company_profile.email,
    }
    for key, value in required_company.items():
        if not (value or "").strip():
            company_missing_fields.append(key)
    if not company_profile.has_any_payment_method():
        company_missing_fields.append("documents.company_required.payment")

    context = build_project_context(
        db,
        request,
        project,
        lang,
        worktypes=worktypes,
        cost_categories=cost_categories,
        workers=workers,
        materials=materials,
        rooms=rooms,
        finance_summary=finance_summary,
        recent_invoices=recent_invoices,
        baseline=baseline,
        geometry_summary=geometry_summary,
        total_labor_hours=calculate_project_total_hours(db, project.id),
        pricing_totals=calculate_project_pricing_totals(project),
        settings_obj=settings,
        estimator_summary=estimator_summary,
        estimator_selected_room_ids=room_ids,
        project_pricing=pricing,
        project_pricing_summary=pricing_summary,
        materials_calc_rows=material_rows,
        materials_calc_totals=material_totals,
        materials_auto_bom=auto_bom,
        workflow_state=build_project_workflow_state(db, project.id, lang=lang),
        active_tab=active_tab,
        company_profile=company_profile,
        documents_doc_type=doc_type,
        documents_offer_lang=offer_lang,
        documents_invoice_lang=invoice_lang,
        documents_selected_lang=selected_doc_lang,
        documents_terms_template=terms_template,
        documents_terms_templates=terms_templates,
        documents_selected_invoice=selected_invoice,
        documents_segment=segment,
        documents_company_missing_fields=company_missing_fields,
        documents_pdf_capability=invoice_pdf_capability(cache=cache),
    )
    return templates.TemplateResponse(request, "projects/detail.html", context)


@router.get("/{project_id}/wizard", response_class=HTMLResponse)
async def project_wizard(
    project_id: int,
    request: Request,
    step: str | None = Query(default=None),
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    cache: RequestCache = Depends(get_request_cache),
):
    resolved_step = _resolve_wizard_step(step)
    if step is None or resolved_step is None:
        return RedirectResponse(url=f"/projects/{project_id}/wizard?step=object&lang={lang}", status_code=status.HTTP_303_SEE_OTHER)

    project = (
        db.query(Project)
        .options(
            selectinload(Project.rooms),
            selectinload(Project.work_items).selectinload(ProjectWorkItem.work_type),
            selectinload(Project.pricing),
            selectinload(Project.invoices),
            selectinload(Project.cost_items).selectinload(ProjectCostItem.category),
            selectinload(Project.worker_assignments).selectinload(ProjectWorkerAssignment.worker),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    context = build_project_context(
        db,
        request,
        project,
        lang,
        wizard_steps=WIZARD_STEPS,
        wizard_step=resolved_step,
        wizard_warning=request.query_params.get("warning"),
        wizard_warning_text=request.query_params.get("warning_text"),
        wizard_summary=_build_wizard_summary(db, project_id, cache=cache),
    )

    if resolved_step == "object":
        context.update(
            {
                "wizard_object_types": WIZARD_OBJECT_TYPES,
                "wizard_room_templates": WIZARD_ROOM_TEMPLATES,
            }
        )
    elif resolved_step == "rooms":
        context["rooms"] = sorted(project.rooms, key=lambda room: room.name.lower() if room.name else "")
    elif resolved_step == "works":
        workspace = build_estimator_workspace(db, project_id, lang=lang)
        templates_list = list_active_packages(db)
        applied_codes = set(list_applied_package_codes(db, project_id))
        package_catalog = [
            {
                "code": template.code,
                "name": package_label(template, lang),
                "description": package_description(template, lang),
                "icon": package_icon(template.code),
            }
            for template in templates_list
        ]
        applied_packages = [item for item in package_catalog if item["code"] in applied_codes]
        context.update(
            {
                "workspace": workspace,
                "package_catalog": package_catalog,
                "applied_packages": applied_packages,
            }
        )
    elif resolved_step == "pricing":
        baseline, scenarios = compute_pricing_scenarios(db, project_id, request_id=getattr(request.state, "request_id", None), cache=cache)
        context.update(
            {
                "pricing": get_or_create_project_pricing(db, project_id),
                "baseline": baseline,
                "scenarios": [_scenario_view_model(scenario) for scenario in scenarios],
            }
        )
    elif resolved_step == "materials":
        context.update(
            {
                "bom": compute_project_bom(db, project_id, cache=cache),
                "shopping_list": compute_project_shopping_list(db, project_id, cache=cache),
            }
        )
    elif resolved_step == "review":
        latest_invoice = (
            db.query(Invoice)
            .filter(Invoice.project_id == project_id)
            .order_by(Invoice.id.desc())
            .first()
        )
        context.update(
            {
                "latest_invoice": latest_invoice,
                "geometry_summary": aggregate_project_geometry(db, project_id, cache=cache),
                "workspace": build_estimator_workspace(db, project_id),
                "shopping_list": compute_project_shopping_list(db, project_id, cache=cache),
                "pricing": get_or_create_project_pricing(db, project_id),
            }
        )
    elif resolved_step == "documents":
        latest_invoice = (
            db.query(Invoice)
            .filter(Invoice.project_id == project_id)
            .order_by(Invoice.id.desc())
            .first()
        )
        context.update({"latest_invoice": latest_invoice})

    return templates.TemplateResponse(request, f"wizard/{resolved_step}.html", context)


@router.post("/{project_id}/wizard/object")
async def project_wizard_object(project_id: int, request: Request, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    form = await request.form()
    lang = str(form.get("lang") or request.query_params.get("lang") or (await get_current_lang(request)))
    object_type = (form.get("object_type") or "").strip().lower()
    template_key = (form.get("object_template") or "").strip().lower()

    if object_type in WIZARD_OBJECT_TYPES:
        project.object_type = object_type
    if template_key:
        project.object_template = template_key
        template_rooms = WIZARD_ROOM_TEMPLATES.get(object_type, {}).get(template_key, [])
        existing_names = {room.name.strip().lower() for room in project.rooms if room.name}
        for room_name in template_rooms:
            if room_name.lower() in existing_names:
                continue
            db.add(Room(project_id=project_id, name=room_name))

    db.add(project)
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/wizard?step=rooms&lang={lang}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/wizard/packages/apply")
async def project_wizard_apply_package(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    form = await request.form()
    package_code = (form.get("package_code") or "").strip()
    scope_mode = (form.get("scope_mode") or form.get("scope_apply_mode") or "WHOLE_PROJECT").strip().upper()
    room_values = form.getlist("selected_room_ids") or form.getlist("room_ids") or form.getlist("room_ids[]")
    selected_room_ids = [int(room_id) for room_id in room_values if str(room_id).isdigit()]

    t = make_t(lang)
    if scope_mode == "SELECTED_ROOMS" and not selected_room_ids:
        add_flash_message(request, t("projects.work_items.empty_selected_rooms"), "error")
        return RedirectResponse(
            url=f"/projects/{project_id}/wizard?step=works&lang={lang}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    summary = apply_package(
        db,
        project_id=project_id,
        package_code=package_code,
        scope_mode=scope_mode,
        selected_room_ids=selected_room_ids,
    )
    if summary.missing_work_type_codes:
        missing_preview = ", ".join(summary.missing_work_type_codes[:5])
        if len(summary.missing_work_type_codes) > 5:
            missing_preview += ", ..."
        add_flash_message(
            request,
            f"{t('estimator.bulk.preset_not_found')}: {missing_preview}",
            "error",
        )
    elif summary.created_count == 0 and summary.updated_count == 0:
        add_flash_message(request, t("estimator.bulk.preset_not_found"), "error")
    else:
        recalc_estimator_project(db, project_id)
        add_flash_message(
            request,
            t("wizard.packages.applied").format(created=summary.created_count, updated=summary.updated_count),
            "success",
        )

    return RedirectResponse(
        url=f"/projects/{project_id}/wizard?step=works&lang={lang}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{project_id}/wizard/packages/remove")
async def project_wizard_remove_package(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    form = await request.form()
    package_code = (form.get("package_code") or "").strip()
    summary = remove_package(db, project_id=project_id, package_code=package_code)
    recalc_estimator_project(db, project_id)
    t = make_t(lang)
    add_flash_message(request, t("wizard.packages.removed").format(deleted=summary.deleted_count), "success")
    return RedirectResponse(
        url=f"/projects/{project_id}/wizard?step=works&lang={lang}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{project_id}/wizard/next")
async def project_wizard_next(project_id: int, request: Request, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    form = await request.form()
    step = _resolve_wizard_step(str(form.get("step") or "object")) or "object"
    lang = str(form.get("lang") or request.query_params.get("lang") or (await get_current_lang(request)))
    next_step = WIZARD_NEXT_STEP.get(step, step)
    warning = None
    warning_text = None

    if step == "rooms":
        rooms_count = db.query(Room).filter(Room.project_id == project_id).count()
        if rooms_count == 0:
            warning = "rooms_empty"
            warning_text = "wizard.warning.rooms_empty"
    elif step == "works":
        items_count = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).count()
        if items_count == 0:
            warning = "works_empty"
            warning_text = "wizard.warning.works_empty"
    elif step == "pricing":
        pricing = get_or_create_project_pricing(db, project_id)
        if not pricing.mode:
            warning = "pricing_missing"
            warning_text = "wizard.warning.pricing_missing"

    redirect_url = f"/projects/{project_id}/wizard?step={next_step}&lang={lang}"
    if warning and warning_text:
        redirect_url = f"{redirect_url}&warning={warning}&warning_text={warning_text}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/wizard/back")
async def project_wizard_back(project_id: int, request: Request, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    form = await request.form()
    step = _resolve_wizard_step(str(form.get("step") or "object")) or "object"
    lang = str(form.get("lang") or request.query_params.get("lang") or (await get_current_lang(request)))
    prev_step = WIZARD_PREV_STEP.get(step, step)
    return RedirectResponse(url=f"/projects/{project_id}/wizard?step={prev_step}&lang={lang}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/documents/preferences")
async def update_project_documents_preferences(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role(ADMIN_ROLE, OPERATOR_ROLE)),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    form = await request.form()
    doc_type = (form.get("doc_type") or "offer").strip().lower()
    doc_lang = normalize_document_lang(form.get("document_lang"), fallback=normalize_document_lang(_lang))
    if doc_type == "offer":
        project.offer_document_lang = doc_lang
        db.add(project)
    elif doc_type == "invoice":
        invoice_id = form.get("invoice_id")
        if invoice_id and str(invoice_id).isdigit():
            invoice = db.get(Invoice, int(invoice_id))
            if invoice and invoice.project_id == project_id:
                invoice.document_lang = doc_lang
                db.add(invoice)
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}?tab=documents&doc_type={doc_type}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{project_id}/workflow", response_class=HTMLResponse)
async def project_workflow(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    state = build_project_workflow_state(db, project_id, lang=lang)
    context = template_context(request, lang)
    context.update(state)
    return templates.TemplateResponse(request, "projects/workflow.html", context)


@router.post("/{project_id}/workflow/recalculate")
async def workflow_recalculate(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    cache: RequestCache = Depends(get_request_cache),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    recalculate_project_work_items(db, project)
    lock = validate_estimate_invariants(project)
    if not lock.ok:
        logger.error(
            "correctness_lock_failed action=workflow_recalculate route=%s project_id=%s request_id=%s user_email=%s errors=%s",
            request.url.path,
            project_id,
            getattr(request.state, "request_id", None),
            request.session.get("user_email"),
            lock.errors,
        )
        add_flash_message(request, make_t(lang)("correctness.lock_failed"), "error")
        return RedirectResponse(url=f"/projects/{project_id}/workflow", status_code=status.HTTP_303_SEE_OTHER)
    add_flash_message(request, make_t(lang)("estimator.recalculated"), "success")
    return RedirectResponse(url=f"/projects/{project_id}/workflow", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/workflow/select-pricing-mode")
async def workflow_select_pricing_mode(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    form = await request.form()
    mode = (form.get("mode") or "").strip().upper()
    pricing = get_or_create_project_pricing(db, project_id)
    try:
        select_pricing_mode(db, pricing=pricing, mode=mode, user_id=request.session.get("user_email"))
        project = db.get(Project, project_id)
        lock = validate_pricing_invariants(db, project)
        if not lock.ok:
            logger.error(
                "correctness_lock_failed action=workflow_select_pricing_mode route=%s project_id=%s request_id=%s user_email=%s errors=%s",
                request.url.path,
                project_id,
                getattr(request.state, "request_id", None),
                request.session.get("user_email"),
                lock.errors,
            )
            add_flash_message(request, make_t(lang)("correctness.lock_failed"), "error")
            return RedirectResponse(url=f"/projects/{project_id}/workflow", status_code=status.HTTP_303_SEE_OTHER)
        add_flash_message(request, make_t(lang)("workflow.flash.pricing_selected"), "success")
    except PricingValidationError:
        add_flash_message(request, make_t(lang)("workflow.flash.pricing_select_error"), "error")
    return RedirectResponse(url=f"/projects/{project_id}/workflow", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/workflow/create-offer-draft")
async def workflow_create_offer_draft(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    state = build_project_workflow_state(db, project_id, lang=lang)
    if not state["can_create_offer"]:
        add_flash_message(request, make_t(lang)(state["blocking_reasons"][0] if state["blocking_reasons"] else "workflow.flash.offer_blocked"), "error")
        return RedirectResponse(url=f"/projects/{project_id}/workflow", status_code=status.HTTP_303_SEE_OTHER)
    project = state["project"]
    if project.offer_status == "issued":
        add_flash_message(request, make_t(lang)("workflow.flash.offer_already_issued"), "warning")
        return RedirectResponse(url=f"/projects/{project_id}/offer", status_code=status.HTTP_303_SEE_OTHER)
    offer_commercial = compute_offer_commercial(db, project.id, lang=lang)
    project.offer_commercial_snapshot = serialize_offer_commercial(offer_commercial)
    project.offer_status = "draft"
    lock = validate_offer_invariants(db, project)
    if not lock.ok:
        logger.error(
            "correctness_lock_failed action=workflow_create_offer_draft route=%s project_id=%s request_id=%s user_email=%s errors=%s",
            request.url.path,
            project_id,
            getattr(request.state, "request_id", None),
            request.session.get("user_email"),
            lock.errors,
        )
        add_flash_message(request, make_t(lang)("correctness.lock_failed"), "error")
        return RedirectResponse(url=f"/projects/{project_id}/workflow", status_code=status.HTTP_303_SEE_OTHER)
    db.add(project)
    db.commit()
    add_flash_message(request, make_t(lang)("workflow.flash.offer_draft_ready"), "success")
    return RedirectResponse(url=f"/projects/{project_id}/offer", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/workflow/create-invoice-draft")
async def workflow_create_invoice_draft(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    state = build_project_workflow_state(db, project_id, lang=lang)
    if not state["can_create_invoice"]:
        add_flash_message(request, make_t(lang)(state["blocking_reasons"][0] if state["blocking_reasons"] else "workflow.flash.invoice_blocked"), "error")
        return RedirectResponse(url=f"/projects/{project_id}/workflow", status_code=status.HTTP_303_SEE_OTHER)

    invoice = (
        db.query(Invoice)
        .filter(Invoice.source_project_id == project_id, Invoice.status == "draft")
        .order_by(Invoice.id.desc())
        .first()
    )
    if invoice is None:
        from datetime import date as dt_date

        invoice = Invoice(
            project_id=project_id,
            source_project_id=project_id,
            invoice_number=None,
            issue_date=dt_date.today(),
            due_date=None,
            paid_date=None,
            status="draft",
            work_sum_without_moms=Decimal("0.00"),
            moms_amount=Decimal("0.00"),
            rot_amount=Decimal("0.00"),
            client_pays_total=Decimal("0.00"),
        )
        db.add(invoice)
        db.flush()
    generate_invoice_lines_from_project(
        db,
        project_id=project_id,
        invoice_id=invoice.id,
        include_labor=True,
        include_materials=True,
        merge_strategy=MERGE_REPLACE_ALL,
        user_id=request.session.get("user_email"),
    )
    db.commit()
    db.refresh(invoice)
    lock = validate_invoice_invariants(db, invoice)
    if not lock.ok:
        logger.error(
            "correctness_lock_failed action=workflow_create_invoice_draft route=%s project_id=%s invoice_id=%s request_id=%s user_email=%s errors=%s",
            request.url.path,
            project_id,
            invoice.id,
            getattr(request.state, "request_id", None),
            request.session.get("user_email"),
            lock.errors,
        )
        add_flash_message(request, make_t(lang)("correctness.lock_failed"), "warning")
    add_flash_message(request, make_t(lang)("workflow.flash.invoice_draft_ready"), "success")
    return RedirectResponse(url=f"/projects/{project_id}/invoices/{invoice.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/estimator-pricing-mode")
async def update_estimator_pricing_mode(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    form = await request.form()
    mode = (form.get("project_pricing_mode") or "").lower()
    mode_map = {"hourly": "HOURLY", "per_m2": "PER_M2", "fixed": "FIXED_TOTAL"}
    if mode not in mode_map:
        raise HTTPException(status_code=400, detail="Unknown pricing mode")
    pricing = get_or_create_project_pricing(db, project_id)
    errors: list[str] = []
    hourly_rate = _parse_local_decimal(form.get("hourly_rate"))
    sqm_rate = _parse_local_decimal(form.get("sqm_rate"))
    fixed_price_amount = _parse_local_decimal(form.get("fixed_price_amount"))
    sqm_basis = (form.get("sqm_basis") or "walls_ceilings").lower()
    sqm_custom_value = _parse_local_decimal(form.get("sqm_custom_value"))
    if mode == "hourly" and (hourly_rate is None or hourly_rate < 0):
        errors.append("pricing.validation.hourly_rate_required")
    if mode == "per_m2":
        if sqm_rate is None or sqm_rate < 0:
            errors.append("pricing.validation.sqm_rate_required")
        if sqm_basis == "custom" and (sqm_custom_value is None or sqm_custom_value < 0):
            errors.append("pricing.validation.sqm_custom_required")
    if mode == "fixed" and (fixed_price_amount is None or fixed_price_amount < 0):
        errors.append("pricing.validation.fixed_price_required")
    if errors:
        for code in errors:
            add_flash_message(request, code, "error")
        return RedirectResponse(url=_project_redirect_with_tab(project_id, request, "scope"), status_code=status.HTTP_303_SEE_OTHER)

    pricing.mode = mode_map[mode]
    pricing.pricing_mode = mode
    pricing.hourly_rate = hourly_rate if hourly_rate is not None else Decimal("0")
    pricing.sqm_rate = sqm_rate if sqm_rate is not None else Decimal("0")
    pricing.sqm_basis = sqm_basis
    pricing.sqm_custom_value = sqm_custom_value
    pricing.fixed_price_amount = fixed_price_amount if fixed_price_amount is not None else Decimal("0")
    pricing.currency = (form.get("currency") or "SEK")[:3]
    pricing.include_materials_in_sell_price = parse_checkbox(form.get("include_materials_in_sell_price"))
    pricing.markup_percent = _parse_local_decimal(form.get("markup_percent")) or Decimal("0")
    pricing.rounding_mode = (form.get("rounding_mode") or "none").lower()
    pricing.hourly_rate_override = pricing.hourly_rate
    pricing.rate_per_m2 = pricing.sqm_rate
    pricing.fixed_total_price = pricing.fixed_price_amount
    pricing.include_materials = pricing.include_materials_in_sell_price
    db.add(pricing)
    db.commit()
    return RedirectResponse(url=_project_redirect_with_tab(project_id, request, "scope"), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{project_id}/edit")
async def edit_project_form(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    cache: RequestCache = Depends(get_request_cache),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    clients = db.query(Client).all()
    context = build_project_context(db, request, project, lang, clients=clients)
    return templates.TemplateResponse(request, "projects/form.html", context)


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
    project.client_id = parse_int_field(client_id, field_name="client_id") if client_id else None
    project.address = clean_str(form.get("address"))
    project.description = clean_str(form.get("description"))
    project.use_rot = parse_checkbox(form.get("use_rot"))
    project.status = clean_str(form.get("status")) or project.status
    project.planned_start_date = _parse_date(form.get("planned_start_date"))
    project.planned_end_date = _parse_date(form.get("planned_end_date"))
    project.actual_start_date = _parse_date(form.get("actual_start_date"))
    project.actual_end_date = _parse_date(form.get("actual_end_date"))

    db.add(project)
    if not safe_commit(db, request, message="update_project"):
        add_flash_message(request, make_t(lang)("common.update_error_retry"), "error")
        return RedirectResponse(url=f"/projects/{project.id}/edit", status_code=status.HTTP_303_SEE_OTHER)

    return RedirectResponse(url=_project_redirect_with_tab(project.id, request, "overview"), status_code=status.HTTP_303_SEE_OTHER)


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
    lang: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: str = Depends(require_auth),
):
    """
    Показывает чистый оферт-документ для клиента.
    """

    view = request.query_params.get("view", "client")
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

    lang = normalize_document_lang(lang, fallback=normalize_document_lang(project.offer_document_lang))

    recalculate_project_work_items(db, project)
    calculate_project_totals(db, project)

    if project.offer_status == "issued":
        snap = read_commercial_snapshot(db, doc_type=SNAP_OFFER, doc_id=project.id)
        commercial = None
        if snap:
            commercial = {
                "mode": snap["mode"],
                "units": snap["units"],
                "rate": snap["rates"],
                "line_items": snap["line_items"],
                "price_ex_vat": Decimal(str(snap["totals"].get("price_ex_vat") or 0)),
                "vat_amount": Decimal(str(snap["totals"].get("vat_amount") or 0)),
                "price_inc_vat": Decimal(str(snap["totals"].get("price_inc_vat") or 0)),
                "warnings": [],
                "math_breakdown": {},
                "sections": [{"id": "default", "title": "", "order": 10, "lines": snap["line_items"]}],
                "summary": {
                    "subtotal_ex_vat": Decimal(str(snap["totals"].get("price_ex_vat") or 0)),
                    "vat_amount": Decimal(str(snap["totals"].get("vat_amount") or 0)),
                    "total_inc_vat": Decimal(str(snap["totals"].get("price_inc_vat") or 0)),
                },
                "metadata": {},
            }
        if commercial is None:
            commercial = deserialize_offer_commercial(project.offer_commercial_snapshot)
    else:
        commercial = None
    if commercial is None:
        offer_commercial = compute_offer_commercial(db, project.id, lang=lang)
        commercial = {
            "mode": offer_commercial.mode,
            "units": offer_commercial.units,
            "line_items": offer_commercial.line_items,
            "price_ex_vat": offer_commercial.price_ex_vat,
            "vat_amount": offer_commercial.vat_amount,
            "price_inc_vat": offer_commercial.price_inc_vat,
            "warnings": offer_commercial.warnings,
            "math_breakdown": offer_commercial.math_breakdown,
            "sections": offer_commercial.sections,
            "summary": offer_commercial.summary,
            "metadata": offer_commercial.metadata,
        }

    legal_notes = {
        note.code: note
        for note in db.query(LegalNote)
        .filter(LegalNote.code.in_(["ROT_BASICS", "MOMS_BASICS"]))
        .all()
    }

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
    context = build_project_context(
        db,
        request,
        project,
        lang,
        client=project.client,
        work_items=commercial["line_items"],
        commercial=commercial,
        offer_date=project.created_at.date() if project.created_at else date.today(),
        legal_notes=legal_notes,
        company_profile=company_profile,
        offer_number=project.offer_number,
        offer_status=project.offer_status,
        stale_warning=is_offer_snapshot_stale(db, project.id, commercial),
        offer_view=view if view in {"client", "internal"} else "client",
        terms_title=terms_title,
        terms_body=terms_body,
    )

    return templates.TemplateResponse(request, "projects/offer.html", context)


def _preview_rooms_import(db: Session, project_id: int, headers: list[str], rows: list[dict[str, str]]) -> dict:
    issues: list[dict] = []
    actions: list[dict] = []
    existing_rooms = {room.id: room for room in db.query(Room).filter(Room.project_id == project_id).all()}
    room_by_name = {room.name.strip().lower(): room for room in existing_rooms.values() if room.name}
    seen_ids: set[int] = set()
    new_names: set[str] = set()
    unknown_columns = [column for column in headers if column not in ROOMS_EXPORT_COLUMNS]
    for column in unknown_columns:
        issues.append({"row": 0, "severity": "WARNING", "message": f"Unknown column ignored: {column}"})
    for index, row in enumerate(rows, start=2):
        row_issues: list[dict] = []
        room_id_value = row.get("room_id", "")
        room_id = int(room_id_value) if room_id_value.isdigit() else None
        if room_id is not None:
            if room_id in seen_ids:
                row_issues.append({"row": index, "severity": "BLOCK", "message": f"Duplicate room_id in file: {room_id}"})
            seen_ids.add(room_id)
        name = (row.get("name") or "").strip()
        if not name:
            row_issues.append({"row": index, "severity": "BLOCK", "message": "name is required"})
        floor_area = _parse_csv_decimal(row.get("floor_area_m2"))
        if floor_area is None or floor_area <= 0:
            row_issues.append({"row": index, "severity": "BLOCK", "message": "floor_area_m2 must be greater than 0"})
        perimeter = _parse_csv_decimal(row.get("perimeter_m"))
        if perimeter is not None and perimeter <= 0:
            row_issues.append({"row": index, "severity": "BLOCK", "message": "perimeter_m must be greater than 0"})
        if perimeter is None:
            row_issues.append({"row": index, "severity": "WARNING", "message": "perimeter_m is empty"})
        height = _parse_csv_decimal(row.get("ceiling_height_m"))
        if height is None or height <= 0:
            row_issues.append({"row": index, "severity": "BLOCK", "message": "ceiling_height_m must be greater than 0"})

        if room_id is not None:
            existing = existing_rooms.get(room_id)
            if not existing:
                row_issues.append({"row": index, "severity": "BLOCK", "message": f"room_id {room_id} not found in this project"})
            action = "update"
        else:
            action = "create"
            lowered_name = name.lower()
            if lowered_name in room_by_name or lowered_name in new_names:
                row_issues.append({"row": index, "severity": "BLOCK", "message": f"Duplicate room name for create: {name}"})
            new_names.add(lowered_name)

        issues.extend(row_issues)
        actions.append(
            {
                "row": index,
                "action": action,
                "room_id": room_id,
                "name": name,
                "floor_area_m2": row.get("floor_area_m2", ""),
                "perimeter_m": row.get("perimeter_m", ""),
                "ceiling_height_m": row.get("ceiling_height_m", ""),
                "notes": row.get("notes", ""),
                "issues": row_issues,
            }
        )
    block_count = sum(1 for issue in issues if issue["severity"] == "BLOCK")
    return {
        "type": "rooms",
        "headers": headers,
        "rows": actions,
        "issues": issues,
        "created": sum(1 for action in actions if action["action"] == "create"),
        "updated": sum(1 for action in actions if action["action"] == "update"),
        "block_count": block_count,
        "warning_count": sum(1 for issue in issues if issue["severity"] == "WARNING"),
    }


def _preview_work_items_import(db: Session, project_id: int, headers: list[str], rows: list[dict[str, str]]) -> dict:
    issues: list[dict] = []
    actions: list[dict] = []
    existing_items = {item.id: item for item in db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).all()}
    rooms = db.query(Room).filter(Room.project_id == project_id).all()
    room_by_id = {room.id: room for room in rooms}
    room_by_name = {room.name.strip().lower(): room for room in rooms if room.name}
    work_types = db.query(WorkType).all()
    wt_by_code = {wt.code.strip().lower(): wt for wt in work_types if wt.code}
    wt_by_name = {wt.name_ru.strip().lower(): wt for wt in work_types if wt.name_ru}
    wt_by_name.update({wt.name_sv.strip().lower(): wt for wt in work_types if wt.name_sv})

    unknown_columns = [column for column in headers if column not in WORK_ITEMS_EXPORT_COLUMNS]
    for column in unknown_columns:
        issues.append({"row": 0, "severity": "WARNING", "message": f"Unknown column ignored: {column}"})

    for index, row in enumerate(rows, start=2):
        row_issues: list[dict] = []
        item_id_value = row.get("item_id", "")
        item_id = int(item_id_value) if item_id_value.isdigit() else None
        quantity = _parse_csv_decimal(row.get("quantity"))
        if quantity is None or quantity <= 0:
            row_issues.append({"row": index, "severity": "BLOCK", "message": "quantity must be greater than 0"})

        room = None
        room_id_value = row.get("room_id", "")
        room_id = int(room_id_value) if room_id_value.isdigit() else None
        if room_id is not None:
            room = room_by_id.get(room_id)
        if room is None:
            room_name = (row.get("room_name") or "").strip().lower()
            room = room_by_name.get(room_name) if room_name else None
        if room is None:
            row_issues.append({"row": index, "severity": "BLOCK", "message": "Room not found by room_id/room_name"})

        work_type = None
        wt_code = (row.get("work_type_code") or "").strip().lower()
        if wt_code:
            work_type = wt_by_code.get(wt_code)
        if work_type is None:
            wt_name = (row.get("work_type_name") or "").strip().lower()
            work_type = wt_by_name.get(wt_name) if wt_name else None
        if work_type is None:
            row_issues.append({"row": index, "severity": "BLOCK", "message": "Work type not found by code/name"})

        if item_id is not None and item_id not in existing_items:
            row_issues.append({"row": index, "severity": "BLOCK", "message": f"item_id {item_id} not found in this project"})

        issues.extend(row_issues)
        actions.append(
            {
                "row": index,
                "action": "update" if item_id is not None else "create",
                "item_id": item_id,
                "room_id": room.id if room else None,
                "room_name": room.name if room else row.get("room_name", ""),
                "work_type_id": work_type.id if work_type else None,
                "work_type_code": work_type.code if work_type else row.get("work_type_code", ""),
                "quantity": row.get("quantity", ""),
                "unit": row.get("unit", ""),
                "notes": row.get("notes", ""),
                "issues": row_issues,
            }
        )
    block_count = sum(1 for issue in issues if issue["severity"] == "BLOCK")
    return {
        "type": "workitems",
        "headers": headers,
        "rows": actions,
        "issues": issues,
        "created": sum(1 for action in actions if action["action"] == "create"),
        "updated": sum(1 for action in actions if action["action"] == "update"),
        "block_count": block_count,
        "warning_count": sum(1 for issue in issues if issue["severity"] == "WARNING"),
    }


@router.get("/{project_id}/rooms/export.csv")
async def export_rooms_csv(project_id: int, request: Request, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    output = io.StringIO()
    writer = csv.writer(output, delimiter=",")
    writer.writerow(ROOMS_EXPORT_COLUMNS)
    rooms = db.query(Room).filter(Room.project_id == project_id).order_by(Room.id.asc()).all()
    for room in rooms:
        writer.writerow([room.id, room.name or "", room.floor_area_m2 or "", room.wall_perimeter_m or "", room.wall_height_m or "", room.description or ""])
    _audit_event(request, db, event_type="csv_export_downloaded", project_id=project_id, details={"type": "rooms", "rows": len(rooms)})
    db.commit()
    logger.info("csv_export_downloaded type=rooms project_id=%s rows=%s request_id=%s", project_id, len(rooms), getattr(request.state, "request_id", None))
    return Response(content=output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="rooms_export.csv"'})


@router.get("/{project_id}/work-items/export.csv")
async def export_work_items_csv(project_id: int, request: Request, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    output = io.StringIO()
    writer = csv.writer(output, delimiter=",")
    writer.writerow(WORK_ITEMS_EXPORT_COLUMNS)
    items = (
        db.query(ProjectWorkItem)
        .options(selectinload(ProjectWorkItem.room), selectinload(ProjectWorkItem.work_type))
        .filter(ProjectWorkItem.project_id == project_id)
        .order_by(ProjectWorkItem.id.asc())
        .all()
    )
    for item in items:
        writer.writerow([item.id, item.room_id or "", item.room.name if item.room else "", item.work_type.code if item.work_type else "", item.work_type.name_ru if item.work_type else "", item.quantity or "", item.work_type.unit if item.work_type else "", item.comment or ""])
    _audit_event(request, db, event_type="csv_export_downloaded", project_id=project_id, details={"type": "workitems", "rows": len(items)})
    db.commit()
    logger.info("csv_export_downloaded type=workitems project_id=%s rows=%s request_id=%s", project_id, len(items), getattr(request.state, "request_id", None))
    return Response(content=output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="work_items_export.csv"'})


@router.get("/{project_id}/import")
async def import_page(project_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    context = build_project_context(db, request, project, lang)
    return templates.TemplateResponse(request, "projects/import.html", context)


@router.post("/{project_id}/import/rooms/preview")
async def preview_rooms_import(project_id: int, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db), _: str = Depends(require_role(ADMIN_ROLE, OPERATOR_ROLE))):
    payload = await file.read()
    if len(payload) > MAX_IMPORT_FILE_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 5 MB)")
    headers, rows = _read_csv_rows(payload)
    if not headers:
        raise HTTPException(status_code=400, detail="CSV headers are required")
    if not rows:
        raise HTTPException(status_code=400, detail="CSV file is empty")
    preview = _preview_rooms_import(db, project_id, headers, rows)
    token = f"rooms-{project_id}-{len(rows)}"
    previews = _get_import_previews(request)
    previews[token] = preview
    _audit_event(request, db, event_type="csv_import_previewed", project_id=project_id, details={"type": "rooms", "created": preview["created"], "updated": preview["updated"], "blocks": preview["block_count"]})
    db.commit()
    return JSONResponse({"preview_token": token, **preview})


@router.post("/{project_id}/import/work-items/preview")
async def preview_work_items_import(project_id: int, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db), _: str = Depends(require_role(ADMIN_ROLE, OPERATOR_ROLE))):
    payload = await file.read()
    if len(payload) > MAX_IMPORT_FILE_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 5 MB)")
    headers, rows = _read_csv_rows(payload)
    if not headers:
        raise HTTPException(status_code=400, detail="CSV headers are required")
    if not rows:
        raise HTTPException(status_code=400, detail="CSV file is empty")
    preview = _preview_work_items_import(db, project_id, headers, rows)
    token = f"workitems-{project_id}-{len(rows)}"
    previews = _get_import_previews(request)
    previews[token] = preview
    _audit_event(request, db, event_type="csv_import_previewed", project_id=project_id, details={"type": "workitems", "created": preview["created"], "updated": preview["updated"], "blocks": preview["block_count"]})
    db.commit()
    return JSONResponse({"preview_token": token, **preview})


@router.post("/{project_id}/import/apply")
async def apply_import(project_id: int, request: Request, preview_token: str = Form(...), db: Session = Depends(get_db), _: str = Depends(require_role(ADMIN_ROLE, OPERATOR_ROLE))):
    previews = _get_import_previews(request)
    preview = previews.get(preview_token)
    if not preview:
        raise HTTPException(status_code=400, detail="Preview token missing or expired")
    if preview.get("block_count", 0) > 0:
        raise HTTPException(status_code=400, detail="Import has blocking errors")
    created = 0
    updated = 0
    try:
        if preview["type"] == "rooms":
            for row in preview["rows"]:
                room = db.get(Room, row["room_id"]) if row["room_id"] else Room(project_id=project_id)
                if row["room_id"] and (not room or room.project_id != project_id):
                    raise HTTPException(status_code=400, detail=f"Cross-project room_id: {row['room_id']}")
                room.name = row["name"]
                room.floor_area_m2 = _parse_csv_decimal(row["floor_area_m2"])
                room.wall_perimeter_m = _parse_csv_decimal(row["perimeter_m"])
                room.wall_height_m = _parse_csv_decimal(row["ceiling_height_m"])
                room.description = row.get("notes")
                db.add(room)
                updated += 1 if row["action"] == "update" else 0
                created += 1 if row["action"] == "create" else 0
        else:
            for row in preview["rows"]:
                item = db.get(ProjectWorkItem, row["item_id"]) if row["item_id"] else ProjectWorkItem(project_id=project_id)
                if row["item_id"] and (not item or item.project_id != project_id):
                    raise HTTPException(status_code=400, detail=f"Cross-project item_id: {row['item_id']}")
                item.project_id = project_id
                item.room_id = row["room_id"]
                item.work_type_id = row["work_type_id"]
                item.quantity = _parse_csv_decimal(row["quantity"])
                item.comment = row.get("notes")
                db.add(item)
                updated += 1 if row["action"] == "update" else 0
                created += 1 if row["action"] == "create" else 0
        project = db.get(Project, project_id)
        if project:
            recalculate_project_work_items(db, project)
            calculate_project_totals(db, project)
        _audit_event(request, db, event_type="csv_import_applied", project_id=project_id, details={"type": preview["type"], "created": created, "updated": updated})
        db.commit()
    except Exception:
        db.rollback()
        raise
    previews.pop(preview_token, None)
    logger.info("csv_import_applied type=%s project_id=%s created=%s updated=%s request_id=%s", preview["type"], project_id, created, updated, getattr(request.state, "request_id", None))
    return JSONResponse({"status": "ok", "type": preview["type"], "created": created, "updated": updated})


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
    translator = make_t(lang)
    work_type_id = form.get("work_type_id")
    work_type = db.get(WorkType, int(work_type_id)) if work_type_id else None
    if not work_type:
        raise HTTPException(status_code=400, detail="Work type required")

    difficulty_factor = Decimal(form.get("difficulty_factor") or "1")
    comment = form.get("comment")
    scope_apply_mode = (form.get("scope_apply_mode") or form.get("scope_mode") or form.get("apply_to") or "single_room").strip().lower()
    if scope_apply_mode in {"selected_room", "single_room", "room"}:
        scope_apply_mode = "single_room"
    elif scope_apply_mode in {"project", "project_aggregate"}:
        scope_apply_mode = "project_aggregate"
    elif scope_apply_mode not in {"all_rooms", "selected_rooms"}:
        scope_apply_mode = "single_room"

    layers = Decimal(form.get("layers") or "1")
    pricing_data = _parse_pricing_form(form)
    project_rooms = list(project.rooms)

    pricing_error = _validate_pricing_form(
        pricing_data,
        quantity=Decimal(form.get("quantity") or "1"),
        has_area=bool(project_rooms),
    )
    if pricing_error:
        add_flash_message(request, pricing_error, "error")
        db.rollback()
        return RedirectResponse(url=_project_redirect_with_tab(project.id, request, "scope"), status_code=status.HTTP_303_SEE_OTHER)

    if scope_apply_mode in {"all_rooms", "selected_rooms", "project_aggregate"}:
        selected_room_ids = form.getlist("selected_room_ids") or form.getlist("room_ids")
        result = apply_work_item_to_scope(
            project.id,
            {
                "work_type_id": work_type.id,
                "scope_apply_mode": scope_apply_mode,
                "selected_room_ids": selected_room_ids,
                "layers": layers,
                "difficulty_factor": difficulty_factor,
                "comment": comment,
                "pricing_mode": pricing_data["pricing_mode"],
                "hourly_rate_sek": pricing_data["hourly_rate_sek"],
                "area_rate_sek": pricing_data["area_rate_sek"],
                "fixed_price_sek": pricing_data["fixed_price_sek"],
                "duplicate_mode": form.get("duplicate_mode") or "append",
            },
            db,
        )
        if scope_apply_mode == "selected_rooms" and not selected_room_ids:
            add_flash_message(request, translator("projects.work_items.empty_selected_rooms"), "error")
            db.rollback()
            return RedirectResponse(url=_project_redirect_with_tab(project.id, request, "scope"), status_code=status.HTTP_303_SEE_OTHER)
        missing_geometry_rooms = [warning.split(":", 1)[1] for warning in result.warnings if warning.startswith("missing_geometry:")]
        if missing_geometry_rooms:
            names = ", ".join(missing_geometry_rooms[:5])
            if len(missing_geometry_rooms) > 5:
                names = f"{names}, …"
            add_flash_message(
                request,
                translator("projects.work_items.bulk_skipped_geometry").format(
                    count=len(missing_geometry_rooms),
                    rooms=names,
                ),
                "warning",
            )
        duplicate_rooms = [warning.split(":", 1)[1] for warning in result.warnings if warning.startswith("duplicate_skipped:")]
        if duplicate_rooms:
            names = ", ".join(duplicate_rooms[:5])
            add_flash_message(request, f"{translator('projects.work_items.duplicate_mode.skip')}: {names}", "warning")
        if not result.created_item_ids:
            add_flash_message(request, translator("projects.work_items.bulk_no_valid_rooms"), "error")
            db.rollback()
            return RedirectResponse(url=_project_redirect_with_tab(project.id, request, "scope"), status_code=status.HTTP_303_SEE_OTHER)
        recalculate_project_work_items(db, project)
        calculate_project_totals(db, project)
        add_flash_message(
            request,
            translator("projects.work_items.bulk_result").format(created=result.created_count, skipped=result.skipped_count),
            "success",
        )
        db.commit()
        return RedirectResponse(url=_project_redirect_with_tab(project.id, request, "scope"), status_code=status.HTTP_303_SEE_OTHER)

    room_id = form.get("room_id")
    room = db.get(Room, int(room_id)) if room_id else None
    if room is None:
        add_flash_message(request, translator("projects.work_items.room_required"), "error")
        db.rollback()
        return RedirectResponse(url=_project_redirect_with_tab(project.id, request, "scope"), status_code=status.HTTP_303_SEE_OTHER)

    if room.project_id != project.id:
        raise HTTPException(status_code=400, detail="Room is not part of project")

    quantity = (Decimal(form.get("quantity") or "0") * layers).quantize(Decimal("0.01"))
    single_pricing_error = _validate_pricing_form(pricing_data, quantity=quantity, has_area=True)
    if single_pricing_error:
        add_flash_message(request, single_pricing_error, "error")
        db.rollback()
        return RedirectResponse(url=_project_redirect_with_tab(project.id, request, "scope"), status_code=status.HTTP_303_SEE_OTHER)

    item = ProjectWorkItem(
        project_id=project.id,
        work_type_id=work_type.id,
        scope_mode=SCOPE_MODE_ROOM,
        room_id=room.id,
        quantity=quantity,
        difficulty_factor=difficulty_factor,
        pricing_mode=pricing_data["pricing_mode"],
        hourly_rate_sek=pricing_data["hourly_rate_sek"],
        area_rate_sek=pricing_data["area_rate_sek"],
        fixed_price_sek=pricing_data["fixed_price_sek"],
        comment=comment,
    )
    db.add(item)
    db.flush()
    quality_report = evaluate_project_quality(db, project.id, lang=lang)
    item_issues = [issue for issue in quality_report.issues if issue.entity == "WORK_ITEM" and issue.entity_id == item.id]
    block_issues = [issue for issue in item_issues if issue.severity == "BLOCK"]
    for issue in item_issues:
        add_flash_message(request, issue.message, "error" if issue.severity == "BLOCK" else "warning")
    if block_issues:
        db.rollback()
        return RedirectResponse(url=_project_redirect_with_tab(project.id, request, "scope"), status_code=status.HTTP_303_SEE_OTHER)

    recalculate_project_work_items(db, project)
    calculate_project_totals(db, project)
    db.commit()
    return RedirectResponse(url=_project_redirect_with_tab(project.id, request, "scope"), status_code=status.HTTP_303_SEE_OTHER)


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

    context = build_project_context(db, request, project, lang, item=item, rooms=rooms, worktypes=worktypes)
    return templates.TemplateResponse(request, "projects/work_item_form.html", context)


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
    pricing_data = _parse_pricing_form(form)
    update_pricing_error = _validate_pricing_form(pricing_data, quantity=item.quantity, has_area=room is not None)
    if update_pricing_error:
        add_flash_message(request, update_pricing_error, "error")
        return RedirectResponse(url=f"/projects/{item.project_id}/items/{item.id}/edit", status_code=status.HTTP_303_SEE_OTHER)
    item.pricing_mode = pricing_data["pricing_mode"]
    item.hourly_rate_sek = pricing_data["hourly_rate_sek"]
    item.area_rate_sek = pricing_data["area_rate_sek"]
    item.fixed_price_sek = pricing_data["fixed_price_sek"]
    item.comment = form.get("comment")

    db.add(item)
    db.flush()
    quality_report = evaluate_project_quality(db, item.project_id, lang=lang)
    item_issues = [issue for issue in quality_report.issues if issue.entity == "WORK_ITEM" and issue.entity_id == item.id]
    block_issues = [issue for issue in item_issues if issue.severity == "BLOCK"]
    for issue in item_issues:
        add_flash_message(request, issue.message, "error" if issue.severity == "BLOCK" else "warning")
    if block_issues:
        db.rollback()
        return RedirectResponse(url=f"/projects/{item.project_id}/items/{item.id}/edit", status_code=status.HTTP_303_SEE_OTHER)

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
    return RedirectResponse(url=_project_redirect_with_tab(project_id, request, "scope"), status_code=status.HTTP_303_SEE_OTHER)


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

    return RedirectResponse(url=_project_redirect_with_tab(project.id, request, "scope"), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{project_id}/estimator")
async def project_estimator_workspace(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    workspace = build_estimator_workspace(db, project_id, lang=lang)
    available_modes = [row["mode"] for row in workspace.get("pricing", {}).get("compare_rows", [])]
    visible_modes = request.query_params.getlist("show_modes") or available_modes
    pricing_filter = (request.query_params.get("filter") or "all").strip().lower()
    if pricing_filter not in {"all", "selected"}:
        pricing_filter = "all"
    context = build_project_context(
        db,
        request,
        project,
        lang,
        workspace=workspace,
        worktypes=db.query(WorkType).filter(WorkType.is_active).all(),
        rooms=project.rooms,
        visible_modes=visible_modes,
        pricing_filter=pricing_filter,
    )
    return templates.TemplateResponse(request, "projects/estimator.html", context)


@router.post("/{project_id}/estimator/recalc")
async def project_estimator_recalc(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    recalc_estimator_project(db, project_id)
    build_estimator_workspace(db, project_id, lang=lang)
    add_flash_message(request, make_t(lang)("estimator.recalculated"), "success")
    return RedirectResponse(url=f"/projects/{project_id}/estimator", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/estimator/preset")
async def project_estimator_apply_preset(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    form = await request.form()
    preset = (form.get("preset") or form.get("package_code") or "").strip()
    t = make_t(lang)
    created_count = apply_package_to_project(db, project_id=project_id, package_code=preset)
    if created_count <= 0:
        add_flash_message(request, t("estimator.bulk.preset_not_found"), "error")
        return RedirectResponse(url=f"/projects/{project_id}/estimator", status_code=status.HTTP_303_SEE_OTHER)
    recalc_estimator_project(db, project_id)
    add_flash_message(request, t("estimator.bulk.applied").format(count=created_count), "success")
    return RedirectResponse(url=f"/projects/{project_id}/estimator", status_code=status.HTTP_303_SEE_OTHER)




@router.post("/{project_id}/estimator/packages/add")
async def project_estimator_add_package(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    return await project_estimator_apply_preset(project_id=project_id, request=request, db=db, lang=lang)


@router.post("/{project_id}/estimator/presets/add")
async def project_estimator_apply_preset_alias(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    return await project_estimator_apply_preset(project_id=project_id, request=request, db=db, lang=lang)


@router.post("/{project_id}/estimator/select-pricing")
async def project_estimator_select_pricing(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    pricing = get_or_create_project_pricing(db, project_id)
    form = await request.form()
    mode = form.get("mode") or "HOURLY"
    select_pricing_mode(db, pricing=pricing, mode=mode, user_id=get_current_user_email(request))
    return RedirectResponse(url=f"/projects/{project_id}/estimator", status_code=status.HTTP_303_SEE_OTHER)




@router.post("/{project_id}/estimator/recalculate")
async def project_estimator_recalculate_alias(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    return await project_estimator_recalc(project_id=project_id, request=request, db=db, lang=lang)


@router.post("/{project_id}/estimator/apply-best-mode")
async def project_estimator_apply_best_mode(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    workspace = build_estimator_workspace(db, project_id)
    compare_rows = workspace.get("pricing", {}).get("compare_rows", [])
    valid_rows = [r for r in compare_rows if not r.get("invalid") and r.get("is_valid", True)]
    if not valid_rows:
        add_flash_message(request, NO_VALID_PRICING_SCENARIO, "warning")
        return RedirectResponse(url=f"/projects/{project_id}/estimator", status_code=status.HTTP_303_SEE_OTHER)
    best = max(valid_rows, key=lambda row: Decimal(str(row.get("profit") or 0)))
    pricing = get_or_create_project_pricing(db, project_id)
    select_pricing_mode(db, pricing=pricing, mode=best["mode"], user_id=get_current_user_email(request))
    return RedirectResponse(url=f"/projects/{project_id}/estimator", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/estimator/apply-mode")
async def project_estimator_apply_mode(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    pricing = get_or_create_project_pricing(db, project_id)
    form = await request.form()
    mode = form.get("mode") or "HOURLY"
    select_pricing_mode(db, pricing=pricing, mode=mode, user_id=get_current_user_email(request))
    return RedirectResponse(url=f"/projects/{project_id}/estimator", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/estimator/work-items/add")
@router.post("/{project_id}/estimator/items/add")
async def project_estimator_add_item(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    form = await request.form()
    work_type_id = int(form.get("work_type_id") or 0)
    work_type = db.get(WorkType, work_type_id)
    if not work_type:
        raise HTTPException(status_code=400, detail="Work type required")
    item = ProjectWorkItem(
        project_id=project_id,
        work_type_id=work_type_id,
        room_id=None,
        quantity=Decimal("1"),
        difficulty_factor=Decimal("1"),
        scope_mode="PROJECT",
        basis_type="wall_area_m2",
        pricing_mode="HOURLY",
        hourly_rate_ex_vat=Decimal("0"),
        norm_hours_per_unit=work_type.hours_per_unit,
    )
    db.add(item)
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/estimator", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/estimator/work-items/{item_id}/update")
@router.post("/{project_id}/estimator/items/{item_id}/update")
async def project_estimator_update_item(
    project_id: int,
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    item = db.query(ProjectWorkItem).filter(ProjectWorkItem.id == item_id, ProjectWorkItem.project_id == project_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    form = await request.form()
    item.scope_mode = (form.get("scope_mode") or item.scope_mode or "PROJECT").upper()
    item.basis_type = (form.get("basis_type") or item.basis_type or "wall_area_m2").lower()
    item.pricing_mode = (form.get("pricing_mode") or item.pricing_mode or "HOURLY").upper()
    selected_room_ids = [int(room_id) for room_id in form.getlist("selected_room_ids") if str(room_id).isdigit()]
    item.selected_room_ids_json = json.dumps(selected_room_ids) if selected_room_ids else None
    manual_qty = form.get("manual_qty")
    item.manual_qty = Decimal(str(manual_qty)) if manual_qty not in (None, "") else item.manual_qty
    fixed_total = form.get("fixed_total_ex_vat")
    item.fixed_total_ex_vat = Decimal(str(fixed_total)) if fixed_total not in (None, "") else item.fixed_total_ex_vat
    unit_rate = form.get("unit_rate_ex_vat")
    item.unit_rate_ex_vat = Decimal(str(unit_rate)) if unit_rate not in (None, "") else item.unit_rate_ex_vat
    hourly_rate = form.get("hourly_rate_ex_vat")
    item.hourly_rate_ex_vat = Decimal(str(hourly_rate)) if hourly_rate not in (None, "") else item.hourly_rate_ex_vat
    db.add(item)
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/estimator", status_code=status.HTTP_303_SEE_OTHER)




@router.post("/{project_id}/estimator/items/{item_id}/duplicate")
async def project_estimator_duplicate_item(
    project_id: int,
    item_id: int,
    db: Session = Depends(get_db),
):
    item = db.query(ProjectWorkItem).filter(ProjectWorkItem.id == item_id, ProjectWorkItem.project_id == project_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    copy_item = ProjectWorkItem(
        project_id=project_id,
        work_type_id=item.work_type_id,
        room_id=item.room_id,
        quantity=item.quantity,
        difficulty_factor=item.difficulty_factor,
        scope_mode=item.scope_mode,
        basis_type=item.basis_type,
        selected_room_ids_json=item.selected_room_ids_json,
        manual_qty=item.manual_qty,
        pricing_mode=item.pricing_mode,
        unit_rate_ex_vat=item.unit_rate_ex_vat,
        fixed_total_ex_vat=item.fixed_total_ex_vat,
        hourly_rate_ex_vat=item.hourly_rate_ex_vat,
        norm_hours_per_unit=item.norm_hours_per_unit,
        source_group_ref=item.source_group_ref,
        comment=item.comment,
    )
    db.add(copy_item)
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/estimator", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/estimator/work-items/{item_id}/delete")
@router.post("/{project_id}/estimator/items/{item_id}/delete")
async def project_estimator_delete_item(
    project_id: int,
    item_id: int,
    db: Session = Depends(get_db),
):
    item = db.query(ProjectWorkItem).filter(ProjectWorkItem.id == item_id, ProjectWorkItem.project_id == project_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    db.delete(item)
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/estimator", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/recalculate-finance")
async def recalculate_finance(project_id: int, request: Request, db: Session = Depends(get_db)):
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

    return RedirectResponse(url=_project_redirect_with_tab(project.id, request, "overview"), status_code=status.HTTP_303_SEE_OTHER)


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

    return RedirectResponse(url=_project_redirect_with_tab(project.id, request, "overview"), status_code=status.HTTP_303_SEE_OTHER)


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

    return RedirectResponse(url=_project_redirect_with_tab(project.id, request, "overview"), status_code=status.HTTP_303_SEE_OTHER)


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
    context = build_project_context(
        db,
        request,
        project,
        lang,
        cost_item=cost_item,
        cost_categories=cost_categories,
        materials=materials,
    )
    return templates.TemplateResponse(request, "projects/cost_item_form.html", context)


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

    return RedirectResponse(url=_project_redirect_with_tab(project.id, request, "overview"), status_code=status.HTTP_303_SEE_OTHER)


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

    return RedirectResponse(url=_project_redirect_with_tab(project.id, request, "overview"), status_code=status.HTTP_303_SEE_OTHER)


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
    context = build_project_context(db, request, project, lang, assignment=assignment, workers=workers)
    return templates.TemplateResponse(request, "projects/worker_assignment_form.html", context)


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

    return RedirectResponse(url=_project_redirect_with_tab(project.id, request, "overview"), status_code=status.HTTP_303_SEE_OTHER)


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

    return RedirectResponse(url=_project_redirect_with_tab(project.id, request, "overview"), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{project_id}/pricing")
async def project_pricing_screen(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    cache: RequestCache = Depends(get_request_cache),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    pricing = get_or_create_project_pricing(db, project_id)
    baseline, scenarios = compute_pricing_scenarios(db, project_id, request_id=getattr(request.state, "request_id", None), cache=cache)
    policy = get_or_create_pricing_policy(db)
    scenario_views = [_scenario_view_model(scenario, evaluate_floor(baseline, scenario, policy)) for scenario in scenarios]
    segment = (project.client.client_segment if project.client and project.client.client_segment else "ANY")
    completeness_by_mode = {scenario.mode: compute_completeness(db, project_id, mode=scenario.mode, segment=segment, lang=lang) for scenario in scenarios}
    log_event(db, request, "pricing_scenarios_viewed", entity_type="PROJECT", entity_id=project_id, metadata={"project_id": project_id})
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
                    "m2_basis": baseline.m2_basis,
                    "total_floor_m2": str(baseline.total_floor_m2),
                    "total_wall_m2": str(baseline.total_wall_m2),
                    "total_ceiling_m2": str(baseline.total_ceiling_m2),
                    "total_paintable_m2": str(baseline.total_paintable_m2),
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

    effective_by_mode = {scenario.mode: _format_hourly(scenario.effective_hourly_sell_rate) for scenario in scenarios}
    context = build_project_context(
        db,
        request,
        project,
        lang,
        pricing=pricing,
        form_data={
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
        converter_input={},
        conversion_result=None,
        errors={},
        is_readonly=is_readonly,
        baseline=baseline,
        scenarios=scenario_views,
        effective_by_mode=effective_by_mode,
        pricing_policy=policy,
        completeness_by_mode=completeness_by_mode,
        selected_completeness=completeness_by_mode.get(pricing.mode),
        best_mode_by_profit=_pick_best_pricing_mode(scenarios, "profit"),
        best_mode_by_effective_hourly=_pick_best_pricing_mode(scenarios, "effective_hourly"),
    )
    return templates.TemplateResponse(request, "projects/pricing.html", context)


@router.get("/{project_id}/takeoff")
async def project_takeoff_screen(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    takeoff = get_or_create_project_takeoff_settings(db, project_id)
    areas = compute_project_areas(db, project_id)
    context = build_project_context(
        db,
        request,
        project,
        lang,
        takeoff=takeoff,
        areas=areas,
        m2_basis_choices=sorted(M2_BASIS_CHOICES),
        m2_basis_labels_ru=M2_BASIS_LABELS_RU,
        is_readonly=get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE},
    )
    return templates.TemplateResponse(request, "projects/takeoff.html", context)


@router.post("/{project_id}/takeoff")
async def project_takeoff_update(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Insufficient role")

    form = await request.form()
    takeoff = get_or_create_project_takeoff_settings(db, project_id)
    takeoff.m2_basis = validate_m2_basis(form.get("m2_basis"))
    takeoff.include_openings_subtraction = form.get("include_openings_subtraction") in ("on", "true", "1", True, 1)
    db.add(takeoff)
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/takeoff", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{project_id}/paint-settings")
async def project_paint_settings_page(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    settings = get_or_create_project_paint_settings(db, project_id)
    systems = db.query(PaintSystem).filter(PaintSystem.is_active.is_(True)).order_by(PaintSystem.name.asc(), PaintSystem.version.desc()).all()
    report = compute_project_bom(db, project_id)
    context = build_project_context(
        db,
        request,
        project,
        lang,
        paint_settings=settings,
        systems=systems,
        bom=report,
        is_readonly=get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE},
    )
    return templates.TemplateResponse(request, "projects/paint_settings.html", context)


@router.post("/{project_id}/paint-settings")
async def project_paint_settings_update(project_id: int, request: Request, db: Session = Depends(get_db)):
    if get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Insufficient role")
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    form = await request.form()
    settings = get_or_create_project_paint_settings(db, project_id)
    wall_id = form.get("default_wall_paint_system_id")
    ceil_id = form.get("default_ceiling_paint_system_id")
    settings.default_wall_paint_system_id = int(wall_id) if wall_id else None
    settings.default_ceiling_paint_system_id = int(ceil_id) if ceil_id else None
    db.add(settings)
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/paint-settings", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{project_id}/materials-plan")
async def project_materials_plan(
    project_id: int,
    request: Request,
    procurement_strategy: str | None = None,
    supplier_id: int | None = None,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    report = compute_project_bom(db, project_id)
    material_settings = get_or_create_project_material_settings(db, project_id)
    draft_invoice = (
        db.query(Invoice)
        .filter(Invoice.project_id == project_id, Invoice.status == "draft")
        .order_by(Invoice.id.desc())
        .first()
    )
    context = build_project_context(
        db,
        request,
        project,
        lang,
        bom=report,
        procurement_strategy=(procurement_strategy or "CHEAPEST"),
        selected_supplier_id=supplier_id,
        material_settings=material_settings,
        draft_invoice=draft_invoice,
        is_readonly=get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE},
    )
    return templates.TemplateResponse(request, "projects/materials_plan.html", context)


@router.post("/{project_id}/materials-plan/recalc")
async def project_materials_plan_recalc(project_id: int, request: Request, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    compute_project_bom(db, project_id)
    return RedirectResponse(url=f"/projects/{project_id}/materials-plan", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/materials-plan/apply-costs")
async def project_materials_plan_apply_costs(project_id: int, request: Request, db: Session = Depends(get_db)):
    if get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Insufficient role")
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    report = compute_project_bom(db, project_id)
    apply_bom_to_project_cost_items(db, project_id, report)
    return RedirectResponse(url=f"/projects/{project_id}/materials-plan", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/materials-plan/apply-invoice")
async def project_materials_plan_apply_invoice(project_id: int, request: Request, db: Session = Depends(get_db)):
    if get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Insufficient role")
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    report = compute_project_bom(db, project_id)
    apply_bom_to_invoice_material_lines(db, project_id, report)
    return RedirectResponse(url=f"/projects/{project_id}/materials-plan", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/materials-plan/settings")
async def project_materials_plan_update_settings(project_id: int, request: Request, db: Session = Depends(get_db)):
    if get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Insufficient role")
    settings = get_or_create_project_material_settings(db, project_id)
    form = await request.form()
    settings.default_markup_pct = Decimal(str(form.get("default_markup_pct") or "20"))
    settings.use_material_sell_price = form.get("use_material_sell_price") in ("on", "true", "1", True, 1)
    settings.include_materials_in_pricing = form.get("include_materials_in_pricing") in ("on", "true", "1", True, 1)
    settings.use_actual_material_costs = form.get("use_actual_material_costs") in ("on", "true", "1", True, 1)
    db.add(settings)
    pricing = get_or_create_project_pricing(db, project_id)
    pricing.include_materials = settings.include_materials_in_pricing
    db.add(pricing)
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/materials-plan", status_code=status.HTTP_303_SEE_OTHER)




@router.get("/{project_id}/materials/overrides")
async def project_material_overrides_page(project_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    overrides = db.query(MaterialConsumptionOverride).filter(MaterialConsumptionOverride.project_id == project_id).order_by(MaterialConsumptionOverride.id.desc()).all()
    rooms = db.query(Room).filter(Room.project_id == project_id).order_by(Room.name.asc()).all()
    work_types = db.query(WorkType).filter(WorkType.is_active.is_(True)).order_by(WorkType.code.asc()).all()
    materials = db.query(Material).filter(Material.is_active.is_(True)).order_by(Material.name_sv.asc()).all()
    edit_id = request.query_params.get("edit_id")
    edit_override = db.get(MaterialConsumptionOverride, int(edit_id)) if edit_id and edit_id.isdigit() else None
    context = build_project_context(db, request, project, lang, overrides=overrides, rooms=rooms, work_types=work_types, materials=materials, edit_override=edit_override, is_readonly=get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE})
    return templates.TemplateResponse(request, "projects/material_overrides.html", context)


@router.post("/{project_id}/materials/overrides")
async def project_material_overrides_create(project_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    if get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Insufficient role")
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    t = make_t(lang)
    form = await request.form()
    room_id_raw = (form.get("room_id") or "").strip()
    room_id = int(room_id_raw) if room_id_raw.isdigit() else None
    if room_id is not None and not db.query(Room).filter(Room.id == room_id, Room.project_id == project_id).first():
        add_flash_message(request, t("materials.overrides.invalid_room"), "error")
        return RedirectResponse(url=f"/projects/{project_id}/materials/overrides", status_code=status.HTTP_303_SEE_OTHER)

    surface_kind = (form.get("surface_kind") or "").strip()
    unit_basis = (form.get("unit_basis") or "").strip()
    if not _allowed_surface_kind(surface_kind) or not _allowed_unit_basis(unit_basis):
        add_flash_message(request, t("materials.overrides.invalid_fields"), "error")
        return RedirectResponse(url=f"/projects/{project_id}/materials/overrides", status_code=status.HTTP_303_SEE_OTHER)

    qty = _parse_decimal_override(request, form.get("quantity_per_unit"), "materials.overrides.invalid_quantity", t)
    base = _parse_decimal_override(request, form.get("base_unit_size"), "materials.overrides.invalid_base", t)
    if qty is None or base is None or qty <= 0 or base <= 0:
        add_flash_message(request, t("materials.overrides.invalid_positive"), "error")
        return RedirectResponse(url=f"/projects/{project_id}/materials/overrides", status_code=status.HTTP_303_SEE_OTHER)

    waste = None
    if (form.get("waste_factor_percent") or "").strip():
        waste = _parse_decimal_override(request, form.get("waste_factor_percent"), "materials.overrides.invalid_waste", t)
        if waste is None:
            return RedirectResponse(url=f"/projects/{project_id}/materials/overrides", status_code=status.HTTP_303_SEE_OTHER)

    obj = MaterialConsumptionOverride(
        project_id=project_id,
        room_id=room_id,
        work_type_id=int(form.get("work_type_id")),
        material_id=int(form.get("material_id")),
        surface_kind=surface_kind,
        unit_basis=unit_basis,
        quantity_per_unit=qty,
        base_unit_size=base,
        waste_factor_percent=waste,
        comment=(form.get("comment") or "").strip() or None,
        is_active=form.get("is_active") in ("on", "true", "1", True, 1),
    )
    db.add(obj)
    try:
        db.commit()
    except Exception:
        db.rollback()
        add_flash_message(request, t("materials.overrides.duplicate"), "error")
        return RedirectResponse(url=f"/projects/{project_id}/materials/overrides", status_code=status.HTTP_303_SEE_OTHER)

    add_flash_message(request, t("materials.overrides.saved"), "success")
    return RedirectResponse(url=f"/projects/{project_id}/materials-plan", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/materials/overrides/{override_id}/edit")
async def project_material_overrides_edit(project_id: int, override_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    if get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Insufficient role")
    existing = db.get(MaterialConsumptionOverride, override_id)
    if not existing or existing.project_id != project_id:
        raise HTTPException(status_code=404, detail="Override not found")
    t = make_t(lang)
    form = await request.form()
    existing.surface_kind = (form.get("surface_kind") or existing.surface_kind).strip()
    existing.unit_basis = (form.get("unit_basis") or existing.unit_basis).strip()
    existing.quantity_per_unit = Decimal(str(form.get("quantity_per_unit") or existing.quantity_per_unit))
    existing.base_unit_size = Decimal(str(form.get("base_unit_size") or existing.base_unit_size))
    existing.waste_factor_percent = Decimal(str(form.get("waste_factor_percent"))) if (form.get("waste_factor_percent") or "").strip() else None
    existing.comment = (form.get("comment") or "").strip() or None
    existing.is_active = form.get("is_active") in ("on", "true", "1", True, 1)
    if existing.quantity_per_unit <= 0 or existing.base_unit_size <= 0 or not _allowed_surface_kind(existing.surface_kind) or not _allowed_unit_basis(existing.unit_basis):
        add_flash_message(request, t("materials.overrides.invalid_fields"), "error")
        return RedirectResponse(url=f"/projects/{project_id}/materials/overrides?edit_id={override_id}", status_code=status.HTTP_303_SEE_OTHER)
    try:
        db.add(existing)
        db.commit()
    except Exception:
        db.rollback()
        add_flash_message(request, t("materials.overrides.duplicate"), "error")
        return RedirectResponse(url=f"/projects/{project_id}/materials/overrides?edit_id={override_id}", status_code=status.HTTP_303_SEE_OTHER)
    add_flash_message(request, t("materials.overrides.updated"), "success")
    return RedirectResponse(url=f"/projects/{project_id}/materials-plan", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/materials/overrides/{override_id}/delete")
async def project_material_overrides_delete(project_id: int, override_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    if get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Insufficient role")
    existing = db.get(MaterialConsumptionOverride, override_id)
    if not existing or existing.project_id != project_id:
        raise HTTPException(status_code=404, detail="Override not found")
    existing.is_active = False
    db.add(existing)
    db.commit()
    add_flash_message(request, make_t(lang)("materials.overrides.deleted"), "success")
    return RedirectResponse(url=f"/projects/{project_id}/materials-plan", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{project_id}/shopping-list")
async def project_shopping_list_page(project_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang), supplier_id: int | None = None, group_by_supplier: bool = True, include_items_without_price: bool = True, strategy: str | None = None):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    report = compute_project_shopping_list(db, project_id, supplier_id=supplier_id, group_by_supplier=group_by_supplier, include_items_without_price=include_items_without_price, strategy=strategy)
    procurement = get_or_create_procurement_settings(db, project_id)
    suppliers = db.query(Supplier).filter(Supplier.is_active.is_(True)).order_by(Supplier.name.asc()).all()
    draft_invoice = db.query(Invoice).filter(Invoice.project_id == project_id, Invoice.status == "draft").order_by(Invoice.id.desc()).first()
    log_event(db, request, "shopping_list_viewed", entity_type="PROJECT", entity_id=project_id, severity="INFO", metadata={"project_id": project_id, "count": len(report.items), "request_id": getattr(request.state, "request_id", None)})
    context = build_project_context(db, request, project, lang, shopping_list=report, selected_supplier_id=supplier_id, selected_strategy=(strategy or "CHEAPEST"), group_by_supplier=group_by_supplier, include_items_without_price=include_items_without_price, procurement_settings=procurement, suppliers=suppliers, draft_invoice=draft_invoice, rounding_modes=[m.value for m in RoundingMode], is_readonly=get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE})
    return templates.TemplateResponse(request, "projects/shopping_list.html", context)


@router.post("/{project_id}/shopping-list/settings")
async def project_shopping_list_settings(project_id: int, request: Request, db: Session = Depends(get_db)):
    if get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Insufficient role")
    form = await request.form()
    settings = get_or_create_procurement_settings(db, project_id)
    supplier_id = form.get("preferred_supplier_id")
    settings.preferred_supplier_id = int(supplier_id) if supplier_id else None
    settings.auto_select_cheapest = form.get("auto_select_cheapest") in ("on", "true", "1", True, 1)
    settings.allow_substitutions = form.get("allow_substitutions") in ("on", "true", "1", True, 1)
    settings.rounding_mode = RoundingMode(form.get("rounding_mode") or RoundingMode.CEIL_TO_PACKS.value)
    settings.material_pricing_mode = (form.get("material_pricing_mode") or settings.material_pricing_mode or "COST_PLUS_MARKUP").upper()
    settings.material_markup_pct = Decimal(str(form.get("material_markup_pct") or settings.material_markup_pct or "20"))
    settings.round_invoice_materials_to_packs = form.get("round_invoice_materials_to_packs") in ("on", "true", "1", True, 1)
    settings.invoice_material_unit = (form.get("invoice_material_unit") or settings.invoice_material_unit or "PACKS").upper()
    db.add(settings)
    db.add(AuditEvent(event_type="invoice_material_pricing_settings_updated", user_id=request.session.get("user_email"), entity_type="project", entity_id=project_id, details=f"mode={settings.material_pricing_mode};markup={settings.material_markup_pct};unit={settings.invoice_material_unit}"))
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/shopping-list", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{project_id}/shopping-list/export.csv")
async def project_shopping_list_export_csv(project_id: int, request: Request, db: Session = Depends(get_db), supplier_id: int | None = None, group_by_supplier: bool = True, include_items_without_price: bool = True, strategy: str | None = None):
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    report = compute_project_shopping_list(db, project_id, supplier_id=supplier_id, group_by_supplier=group_by_supplier, include_items_without_price=include_items_without_price, strategy=strategy)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["material_name", "planned_qty", "planned_unit", "pack_size", "pack_unit", "packs_needed", "purchase_qty", "supplier", "unit_price", "line_total", "warnings"])
    writer.writeheader()
    for item in report.items:
        writer.writerow({"material_name": item.material_name, "planned_qty": item.planned_qty, "planned_unit": item.planned_unit, "pack_size": item.pack_size or "", "pack_unit": item.pack_unit or "", "packs_needed": item.packs_needed, "purchase_qty": item.purchase_qty, "supplier": item.supplier_name or "", "unit_price": item.unit_price or "", "line_total": item.line_total_cost, "warnings": ",".join(item.warnings)})
    log_event(db, request, "shopping_list_exported_csv", entity_type="PROJECT", entity_id=project_id, severity="INFO", metadata={"project_id": project_id, "count": len(report.items), "request_id": getattr(request.state, "request_id", None)})
    return Response(content=output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="shopping_list.csv"'})


@router.get("/{project_id}/shopping-list/export.pdf")
async def project_shopping_list_export_pdf(project_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang), supplier_id: int | None = None, group_by_supplier: bool = True, include_items_without_price: bool = True, strategy: str | None = None):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    report = compute_project_shopping_list(db, project_id, supplier_id=supplier_id, group_by_supplier=group_by_supplier, include_items_without_price=include_items_without_price, strategy=strategy)
    context = template_context(request, lang)
    context.update({"project": project, "shopping_list": report, "group_by_supplier": group_by_supplier, "export_date": datetime.now(timezone.utc).date().isoformat()})
    html = templates.get_template("pdf/shopping_list_pdf.html").render(context)
    pdf_result = render_pdf_from_html_with_engine(html=html, base_url=PROJECT_ROOT, stylesheet_path=PDF_STYLESHEET)
    log_event(db, request, "shopping_list_exported_pdf", entity_type="PROJECT", entity_id=project_id, severity="INFO", metadata={"project_id": project_id, "count": len(report.items), "request_id": getattr(request.state, "request_id", None)})
    return Response(content=pdf_result.pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="shopping_list.pdf"', REQUEST_ID_HEADER: getattr(request.state, "request_id", ""), "X-PDF-Engine": pdf_result.engine})


@router.get("/{project_id}/shopping-list/print")
async def project_shopping_list_print(project_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang), supplier_id: int | None = None, group_by_supplier: bool = True, include_items_without_price: bool = True, strategy: str | None = None):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    report = compute_project_shopping_list(db, project_id, supplier_id=supplier_id, group_by_supplier=group_by_supplier, include_items_without_price=include_items_without_price, strategy=strategy)
    context = build_project_context(db, request, project, lang, shopping_list=report, group_by_supplier=group_by_supplier, export_date=datetime.now(timezone.utc).date().isoformat())
    return templates.TemplateResponse(request, "projects/shopping_list_print.html", context)


@router.post("/{project_id}/shopping-list/apply-costs")
async def project_shopping_list_apply_costs(project_id: int, request: Request, db: Session = Depends(get_db)):
    if get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Insufficient role")
    report = compute_project_shopping_list(db, project_id)
    try:
        count = apply_shopping_list_to_project_cost_items(db, project_id, report)
    except ValueError:
        raise HTTPException(status_code=409, detail="already applied")
    log_event(db, request, "shopping_list_applied_to_costs", entity_type="PROJECT", entity_id=project_id, severity="INFO", metadata={"project_id": project_id, "count": count, "request_id": getattr(request.state, "request_id", None)})
    return RedirectResponse(url=f"/projects/{project_id}/shopping-list", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/shopping-list/apply-invoice")
async def project_shopping_list_apply_invoice(project_id: int, request: Request, db: Session = Depends(get_db)):
    if get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Insufficient role")
    report = compute_project_shopping_list(db, project_id)
    count = apply_shopping_list_to_invoice_material_lines(db, project_id, report)
    log_event(db, request, "shopping_list_applied_to_invoice", entity_type="PROJECT", entity_id=project_id, severity="INFO", metadata={"project_id": project_id, "count": count, "request_id": getattr(request.state, "request_id", None)})
    return RedirectResponse(url=f"/projects/{project_id}/shopping-list", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{project_id}/materials-actuals")
async def project_materials_actuals_page(project_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    report = compute_materials_plan_vs_actual(db, project_id)
    purchases = db.query(Supplier).filter(Supplier.is_active.is_(True)).order_by(Supplier.name.asc()).all()
    materials = db.query(Material).filter(Material.is_active.is_(True)).order_by(Material.name_sv.asc()).all()
    shopping_list = compute_project_shopping_list(db, project_id)
    log_event(db, request, "plan_vs_actual_viewed", entity_type="PROJECT", entity_id=project_id, metadata={"project_id": project_id, "request_id": getattr(request.state, "request_id", None)})
    context = build_project_context(db, request, project, lang, suppliers=purchases, materials=materials, shopping_list=shopping_list, plan_actual=report, is_readonly=get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE})
    return templates.TemplateResponse(request, "projects/materials_actuals.html", context)




@router.post("/{project_id}/materials-actuals/manual")
async def save_materials_actuals_manual(project_id: int, request: Request, db: Session = Depends(get_db)):
    if get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Insufficient role")
    form = await request.form()
    material_name = (form.get("material_name") or "").strip()
    if not material_name:
        return RedirectResponse(url=f"/projects/{project_id}/materials-actuals", status_code=status.HTTP_303_SEE_OTHER)
    upsert_actual_entry(
        db,
        project_id=project_id,
        material_name=material_name,
        actual_qty=Decimal(form.get("actual_qty") or "0"),
        actual_packages=Decimal(form.get("actual_packages") or "0"),
        actual_cost_sek=Decimal(form.get("actual_cost_sek") or "0"),
        supplier=(form.get("supplier") or None),
        receipt_note=(form.get("receipt_note") or None),
    )
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/materials-actuals", status_code=status.HTTP_303_SEE_OTHER)
@router.post("/{project_id}/materials-actuals/purchases")
async def create_materials_purchase(project_id: int, request: Request, db: Session = Depends(get_db)):
    if get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Insufficient role")
    form = await request.form()
    supplier_id = int(form.get("supplier_id")) if form.get("supplier_id") else None
    user = db.query(User).filter(User.email == get_current_user_email(request)).first()
    lines = []
    material_ids = form.getlist("material_id")
    packs_counts = form.getlist("packs_count")
    pack_sizes = form.getlist("pack_size")
    pack_prices = form.getlist("pack_price_ex_vat")
    units = form.getlist("unit")
    for i, material_id in enumerate(material_ids):
        if not material_id:
            continue
        lines.append({"material_id": int(material_id), "packs_count": packs_counts[i], "pack_size": pack_sizes[i], "pack_price_ex_vat": pack_prices[i], "unit": units[i] or "PCS", "source": "MANUAL"})
    if not lines:
        raise HTTPException(status_code=422, detail="No purchase lines")
    create_material_purchase(db, project_id=project_id, supplier_id=supplier_id, purchased_at=_parse_purchase_datetime(form.get("purchased_at")), invoice_ref=form.get("invoice_ref"), notes=form.get("notes"), currency=form.get("currency") or "SEK", user_id=user.id if user else None, lines=lines)
    return RedirectResponse(url=f"/projects/{project_id}/materials-actuals", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{project_id}/materials-actuals/purchases/from-shopping-list")
async def quick_create_materials_purchase(project_id: int, request: Request, db: Session = Depends(get_db)):
    if get_current_user_role(request) not in {ADMIN_ROLE, OPERATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Insufficient role")
    form = await request.form()
    selected = form.getlist("selected_material_id")
    if not selected:
        raise HTTPException(status_code=422, detail="No shopping list items selected")
    report = compute_project_shopping_list(db, project_id)
    by_material = {str(i.material_id): i for i in report.items}
    lines = []
    payload_for_hash = []
    for mid in selected:
        item = by_material.get(str(mid))
        if not item:
            continue
        packs = Decimal(str(form.get(f"packs_bought_{mid}") or item.packs_count or 0))
        price = Decimal(str(form.get(f"pack_price_ex_vat_{mid}") or item.pack_price_ex_vat or 0))
        lines.append({"material_id": int(mid), "packs_count": packs, "pack_size": item.pack_size or Decimal("1"), "pack_price_ex_vat": price, "unit": item.unit, "vat_rate_pct": item.vat_rate_pct, "source": "SHOPPING_LIST"})
        payload_for_hash.append({"material_id": int(mid), "packs": str(packs), "price": str(price)})
    idem = request.headers.get("Idempotency-Key") or build_quick_add_idempotency_key(project_id, {"selected": sorted(payload_for_hash)})
    user = db.query(User).filter(User.email == get_current_user_email(request)).first()
    create_material_purchase(db, project_id=project_id, supplier_id=None, purchased_at=datetime.now(timezone.utc), invoice_ref=form.get("invoice_ref"), notes="quick_add_from_shopping_list", currency="SEK", user_id=user.id if user else None, lines=lines, idempotency_key=idem)
    return RedirectResponse(url=f"/projects/{project_id}/materials-actuals", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{project_id}/materials-actuals/export-plan-vs-actual.csv")
async def materials_actuals_export_plan_vs_actual_csv(project_id: int, request: Request, db: Session = Depends(get_db)):
    report = compute_materials_plan_vs_actual(db, project_id)
    log_event(db, request, "materials_actuals_exported", entity_type="PROJECT", entity_id=project_id, metadata={"kind": "plan_vs_actual_csv"})
    return Response(content=export_plan_vs_actual_csv(report), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="materials_plan_vs_actual.csv"'})


@router.get("/{project_id}/materials-actuals/export-purchases.csv")
async def materials_actuals_export_purchases_csv(project_id: int, request: Request, db: Session = Depends(get_db)):
    content = export_purchases_csv(db, project_id)
    log_event(db, request, "materials_actuals_exported", entity_type="PROJECT", entity_id=project_id, metadata={"kind": "purchases_csv"})
    return Response(content=content, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="materials_purchases.csv"'})


@router.get("/{project_id}/materials-actuals/export-report.pdf")
async def materials_actuals_export_pdf(project_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    report = compute_materials_plan_vs_actual(db, project_id)
    context = template_context(request, lang)
    context.update({"project": project, "plan_actual": report})
    html = templates.get_template("pdf/materials_actuals_pdf.html").render(context)
    pdf_bytes = export_plan_vs_actual_pdf(html=html, base_url=PROJECT_ROOT, stylesheet_path=PDF_STYLESHEET)
    log_event(db, request, "materials_actuals_exported", entity_type="PROJECT", entity_id=project_id, metadata={"kind": "pdf"})
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="materials_actuals.pdf"'})


@router.post("/{project_id}/pricing")
async def update_project_pricing_screen(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    cache: RequestCache = Depends(get_request_cache),
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
        log_event(
            db,
            request,
            "pricing_conversion_calculated",
            entity_type="PROJECT",
            entity_id=project_id,
            metadata={
                "project_id": project_id,
                "desired_effective_hourly_ex_vat": converter_input["desired_effective_hourly_ex_vat"] or None,
                "desired_margin_pct": converter_input["desired_margin_pct"] or None,
                "warnings": conversion_result.warnings,
            },
        )
        db.commit()

        baseline, scenarios = compute_pricing_scenarios(db, project_id, request_id=getattr(request.state, "request_id", None), cache=cache)
        policy = get_or_create_pricing_policy(db)
        scenario_views = [_scenario_view_model(scenario, evaluate_floor(baseline, scenario, policy)) for scenario in scenarios]
        segment = (project.client.client_segment if project.client and project.client.client_segment else "ANY")
        completeness_by_mode = {scenario.mode: compute_completeness(db, project_id, mode=scenario.mode, segment=segment, lang=lang) for scenario in scenarios}
        context = build_project_context(
            db,
            request,
            project,
            lang,
            pricing=pricing,
            form_data={
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
            converter_input=converter_input,
            conversion_result=_conversion_view_model(conversion_result),
            errors={},
            is_readonly=role not in {ADMIN_ROLE, OPERATOR_ROLE},
            baseline=baseline,
            scenarios=scenario_views,
            effective_by_mode={scenario.mode: _format_hourly(scenario.effective_hourly_sell_rate) for scenario in scenarios},
            pricing_policy=policy,
            completeness_by_mode=completeness_by_mode,
            selected_completeness=completeness_by_mode.get(pricing.mode),
        )
        return templates.TemplateResponse(request, "projects/pricing.html", context)

    if intent == "apply_recommended":
        apply_mode = (payload.get("apply_mode") or "").upper()
        baseline, scenarios = compute_pricing_scenarios(db, project_id, request_id=getattr(request.state, "request_id", None), cache=cache)
        policy = get_or_create_pricing_policy(db)
        selected = next((sc for sc in scenarios if sc.mode == apply_mode), None)
        if selected is None:
            raise HTTPException(status_code=400, detail="Unknown pricing mode")
        floor = evaluate_floor(baseline, selected, policy)
        mode_to_field = {
            "FIXED_TOTAL": ("fixed_total_price", floor.recommended_fixed_total),
            "PER_M2": ("rate_per_m2", floor.recommended_rate_per_m2),
            "PER_ROOM": ("rate_per_room", floor.recommended_rate_per_room),
            "PIECEWORK": ("rate_per_piece", floor.recommended_rate_per_piece),
            "HOURLY": ("hourly_rate_override", floor.recommended_min_price_ex_vat / baseline.labor_hours_total if baseline.labor_hours_total > 0 else None),
        }
        field_name, value = mode_to_field.get(apply_mode, (None, None))
        if field_name is None or value is None:
            raise HTTPException(status_code=400, detail="Recommended value unavailable")
        setattr(pricing, field_name, value.quantize(Decimal("0.01")))
        db.add(pricing)
        db.commit()
        add_flash_message(request, make_t(lang)("projects.takeoff.recommended_applied"), "success")
        return RedirectResponse(url=f"/projects/{project_id}/pricing", status_code=status.HTTP_303_SEE_OTHER)

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
        log_event(db, request, "pricing_conversion_applied", entity_type="PROJECT", entity_id=project_id, metadata={"project_id": project_id, "mode": apply_mode, "value": str(apply_value)})
        db.commit()
        add_flash_message(request, make_t(lang)("projects.takeoff.conversion_applied"), "success")
        return RedirectResponse(url=f"/projects/{project_id}/pricing", status_code=status.HTTP_303_SEE_OTHER)

    if intent == "apply_best_mode":
        baseline, scenarios = compute_pricing_scenarios(db, project_id, request_id=getattr(request.state, "request_id", None), cache=cache)
        del baseline
        best_metric = payload.get("best_metric") or "profit"
        best_mode = _pick_best_pricing_mode(scenarios, metric=best_metric)
        if not best_mode:
            add_flash_message(request, NO_VALID_PRICING_SCENARIO, "warning")
            return RedirectResponse(url=f"/projects/{project_id}/pricing", status_code=status.HTTP_303_SEE_OTHER)
        select_pricing_mode(
            db,
            pricing=pricing,
            mode=best_mode,
            user_id=get_current_user_email(request),
        )
        add_flash_message(request, make_t(lang)("projects.pricing.best_mode_applied"), "success")
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
        baseline, scenarios = compute_pricing_scenarios(db, project_id, request_id=getattr(request.state, "request_id", None), cache=cache)
        policy = get_or_create_pricing_policy(db)
        scenario_views = [_scenario_view_model(scenario, evaluate_floor(baseline, scenario, policy)) for scenario in scenarios]
        segment = (project.client.client_segment if project.client and project.client.client_segment else "ANY")
        completeness_by_mode = {scenario.mode: compute_completeness(db, project_id, mode=scenario.mode, segment=segment, lang=lang) for scenario in scenarios}
        context = build_project_context(
            db,
            request,
            project,
            lang,
            pricing=pricing,
            form_data=payload,
            converter_input=converter_input,
            conversion_result=None,
            errors=exc.errors,
            is_readonly=False,
            baseline=baseline,
            scenarios=scenario_views,
            effective_by_mode={scenario.mode: _format_hourly(scenario.effective_hourly_sell_rate) for scenario in scenarios},
            pricing_policy=policy,
            completeness_by_mode=completeness_by_mode,
            selected_completeness=completeness_by_mode.get(pricing.mode),
        )
        return templates.TemplateResponse(request, "projects/pricing.html", context, status_code=400)

    return RedirectResponse(
        url=f"/projects/{project_id}/pricing", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/{project_id}/buffers")
async def project_buffers_page(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    role = get_current_user_role(request)
    if role not in {ADMIN_ROLE, OPERATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Insufficient role")

    buffer_settings = get_or_create_project_buffer_settings(db, project_id)
    execution_profile = get_or_create_project_execution_profile(db, project_id)
    speed_profiles = db.query(SpeedProfile).filter(SpeedProfile.is_active.is_(True)).order_by(SpeedProfile.code.asc()).all()
    baseline, _ = compute_pricing_scenarios(db, project_id, request_id=getattr(request.state, "request_id", None))
    context = build_project_context(
        db,
        request,
        project,
        lang,
        buffer_settings=buffer_settings,
        baseline=baseline,
        execution_profile=execution_profile,
        speed_profiles=speed_profiles,
    )
    return templates.TemplateResponse(request, "projects/buffers.html", context)


@router.post("/{project_id}/buffers")
async def update_project_buffers(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    role: str = Depends(get_current_user_role),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    role = get_current_user_role(request)
    if role not in {ADMIN_ROLE, OPERATOR_ROLE}:
        raise HTTPException(status_code=403, detail="Insufficient role")

    form = await request.form()
    settings_obj = get_or_create_project_buffer_settings(db, project_id)
    execution_profile = get_or_create_project_execution_profile(db, project_id)
    before = {"include_setup_cleanup_travel": settings_obj.include_setup_cleanup_travel, "include_risk": settings_obj.include_risk}
    settings_obj.include_setup_cleanup_travel = form.get("include_setup_cleanup_travel") in ("on", "true", "1", True, 1)
    settings_obj.include_risk = form.get("include_risk") in ("on", "true", "1", True, 1)
    speed_profile_raw = form.get("speed_profile_id")
    execution_profile.speed_profile_id = int(speed_profile_raw) if speed_profile_raw else None
    db.add(settings_obj)
    db.add(execution_profile)
    log_buffer_audit(
        db,
        actor=get_current_user_email(request) or "system",
        action="UPDATE",
        entity_type="project_buffer_settings",
        entity_id=project_id,
        before=before,
        after={"include_setup_cleanup_travel": settings_obj.include_setup_cleanup_travel, "include_risk": settings_obj.include_risk},
        request_id=getattr(request.state, "request_id", None),
    )
    log_event(db, request, "project_speed_profile_updated", entity_type="PROJECT", entity_id=project.id, metadata={"speed_profile_id": execution_profile.speed_profile_id})
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/buffers", status_code=status.HTTP_303_SEE_OTHER)
