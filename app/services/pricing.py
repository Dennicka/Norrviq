import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session, selectinload

from app.models.audit_event import AuditEvent
from app.models.cost import ProjectCostItem
from app.models.project import Project, ProjectWorkItem, ProjectWorkerAssignment
from app.models.project_pricing import ProjectPricing
from app.models.settings import get_or_create_settings

logger = logging.getLogger("uvicorn.error")

PRICING_MODES = {"HOURLY", "FIXED_TOTAL", "PER_M2", "PER_ROOM", "PIECEWORK"}
DEFAULT_VAT_PCT = Decimal("25.00")
HOURS_QUANT = Decimal("0.01")
MONEY_QUANT = Decimal("0.01")


@dataclass
class ProjectBaseline:
    labor_hours_total: Decimal
    labor_cost_internal: Decimal
    materials_cost_internal: Decimal
    travel_setup_cost_internal: Decimal
    overhead_cost_internal: Decimal
    internal_total_cost: Decimal
    total_m2: Decimal
    rooms_count: int
    items_count: int


@dataclass
class PricingScenario:
    mode: str
    input_params: dict[str, str | None]
    price_ex_vat: Decimal
    vat_amount: Decimal
    price_inc_vat: Decimal
    effective_hourly_sell_rate: Decimal | None
    profit: Decimal
    margin_pct: Decimal | None
    warnings: list[str]
    invalid: bool
    details_lines: list[str]


class PricingValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("Pricing validation failed")
        self.errors = errors


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT)


def _quantize_hours(value: Decimal) -> Decimal:
    return value.quantize(HOURS_QUANT)


def get_or_create_project_pricing(db: Session, project_id: int) -> ProjectPricing:
    pricing = db.query(ProjectPricing).filter(ProjectPricing.project_id == project_id).first()
    if pricing:
        return pricing

    project = db.get(Project, project_id)
    if not project:
        raise ValueError("Project not found")

    pricing = ProjectPricing(project_id=project_id, mode="HOURLY")
    db.add(pricing)
    db.commit()
    db.refresh(pricing)
    return pricing


def _parse_decimal(value: str | None, *, field: str, errors: dict[str, str], allow_empty: bool = True):
    if value is None or value == "":
        if allow_empty:
            return None
        errors[field] = "Обязательное поле"
        return None
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError):
        errors[field] = "Некорректное число"
        return None
    if amount <= 0:
        errors[field] = "Значение должно быть больше 0"
        return None
    return amount.quantize(Decimal("0.01"))


def compute_project_baseline(
    db: Session,
    project_id: int,
    *,
    include_materials: bool,
    include_travel_setup_buffers: bool,
) -> ProjectBaseline:
    project = (
        db.query(Project)
        .options(
            selectinload(Project.work_items).selectinload(ProjectWorkItem.work_type),
            selectinload(Project.rooms),
            selectinload(Project.cost_items).selectinload(ProjectCostItem.category),
            selectinload(Project.worker_assignments).selectinload(ProjectWorkerAssignment.worker),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise ValueError("Project not found")

    settings = get_or_create_settings(db)
    default_worker_rate = Decimal(str(settings.default_worker_hourly_rate or 0))
    employer_pct = Decimal(str(settings.employer_contributions_percent or 0)) / Decimal("100")

    labor_hours_total = Decimal("0")
    salary_fund = Decimal("0")
    for assignment in project.worker_assignments:
        hours = Decimal(str(assignment.actual_hours or assignment.planned_hours or 0))
        worker_rate = assignment.worker.hourly_rate if assignment.worker else None
        hourly_rate = Decimal(str(worker_rate if worker_rate is not None else default_worker_rate))
        labor_hours_total += hours
        salary_fund += hours * hourly_rate

    if labor_hours_total <= 0:
        for item in project.work_items:
            labor_hours_total += Decimal(str(item.calculated_hours or 0))

    labor_hours_total = _quantize_hours(labor_hours_total)
    labor_cost_internal = _quantize_money(salary_fund + (salary_fund * employer_pct))

    materials_cost_internal = Decimal("0")
    travel_setup_cost_internal = Decimal("0")
    other_cost_internal = Decimal("0")
    for item in project.cost_items:
        amount = Decimal(str(item.amount or 0))
        code = item.category.code if item.category else ""
        if code == "MATERIALS" or item.is_material:
            materials_cost_internal += amount
        elif code in {"TRANSPORT", "FUEL", "PARKING", "TRAVEL", "SETUP", "BUFFERS"}:
            travel_setup_cost_internal += amount
        else:
            other_cost_internal += amount

    if not include_materials:
        materials_cost_internal = Decimal("0")
    if not include_travel_setup_buffers:
        travel_setup_cost_internal = Decimal("0")

    materials_cost_internal = _quantize_money(materials_cost_internal)
    travel_setup_cost_internal = _quantize_money(travel_setup_cost_internal)

    overhead_base = labor_cost_internal + materials_cost_internal + travel_setup_cost_internal + other_cost_internal
    overhead_pct = Decimal(str(settings.default_overhead_percent or 0)) / Decimal("100")
    overhead_cost_internal = _quantize_money(overhead_base * overhead_pct)

    internal_total_cost = _quantize_money(
        labor_cost_internal
        + materials_cost_internal
        + travel_setup_cost_internal
        + _quantize_money(other_cost_internal)
        + overhead_cost_internal
    )

    total_m2 = _quantize_hours(
        sum((Decimal(str(room.floor_area_m2 or 0)) for room in project.rooms), Decimal("0"))
    )
    rooms_count = len(project.rooms)
    items_count = len(project.work_items)

    return ProjectBaseline(
        labor_hours_total=labor_hours_total,
        labor_cost_internal=labor_cost_internal,
        materials_cost_internal=materials_cost_internal,
        travel_setup_cost_internal=travel_setup_cost_internal,
        overhead_cost_internal=overhead_cost_internal,
        internal_total_cost=internal_total_cost,
        total_m2=total_m2,
        rooms_count=rooms_count,
        items_count=items_count,
    )


def _build_scenario(
    *,
    mode: str,
    input_params: dict[str, str | None],
    baseline: ProjectBaseline,
    price_ex_vat: Decimal,
    warnings: list[str],
    details_lines: list[str],
    vat_pct: Decimal,
    invalid: bool = False,
) -> PricingScenario:
    price_ex_vat = _quantize_money(price_ex_vat)
    vat_amount = _quantize_money(price_ex_vat * vat_pct / Decimal("100"))
    price_inc_vat = _quantize_money(price_ex_vat + vat_amount)
    effective_hourly_sell_rate = None
    if baseline.labor_hours_total > 0:
        effective_hourly_sell_rate = _quantize_money(price_ex_vat / baseline.labor_hours_total)
    profit = _quantize_money(price_ex_vat - baseline.internal_total_cost)
    margin_pct = None
    if price_ex_vat > 0:
        margin_pct = _quantize_money(profit / price_ex_vat * Decimal("100"))
    return PricingScenario(
        mode=mode,
        input_params=input_params,
        price_ex_vat=price_ex_vat,
        vat_amount=vat_amount,
        price_inc_vat=price_inc_vat,
        effective_hourly_sell_rate=effective_hourly_sell_rate,
        profit=profit,
        margin_pct=margin_pct,
        warnings=warnings,
        invalid=invalid,
        details_lines=details_lines,
    )


def compute_pricing_scenarios(db: Session, project_id: int) -> tuple[ProjectBaseline, list[PricingScenario]]:
    pricing = get_or_create_project_pricing(db, project_id)
    baseline = compute_project_baseline(
        db,
        project_id,
        include_materials=pricing.include_materials,
        include_travel_setup_buffers=pricing.include_travel_setup_buffers,
    )
    settings = get_or_create_settings(db)
    vat_pct = Decimal(str(settings.moms_percent if settings.moms_percent is not None else DEFAULT_VAT_PCT))

    scenarios: list[PricingScenario] = []

    hourly_rate = pricing.hourly_rate_override or settings.hourly_rate_company or Decimal("0")
    hourly_rate = Decimal(str(hourly_rate or 0))
    hourly_price = baseline.labor_hours_total * hourly_rate
    if pricing.include_materials:
        hourly_price += baseline.materials_cost_internal
    details = [
        f"hours({baseline.labor_hours_total}) × hourly_rate({hourly_rate})",
        f"+ materials({baseline.materials_cost_internal})" if pricing.include_materials else "+ materials excluded",
    ]
    scenarios.append(
        _build_scenario(
            mode="HOURLY",
            input_params={"hourly_rate": str(_quantize_money(hourly_rate))},
            baseline=baseline,
            price_ex_vat=hourly_price,
            warnings=[],
            details_lines=details,
            vat_pct=vat_pct,
        )
    )

    scenarios.append(
        _build_scenario(
            mode="FIXED_TOTAL",
            input_params={"fixed_total_price": str(pricing.fixed_total_price) if pricing.fixed_total_price is not None else None},
            baseline=baseline,
            price_ex_vat=Decimal(str(pricing.fixed_total_price or 0)),
            warnings=[] if pricing.fixed_total_price is not None else ["Fixed total price is not set"],
            invalid=pricing.fixed_total_price is None,
            details_lines=[f"fixed_total_price({pricing.fixed_total_price or Decimal('0.00')})"],
            vat_pct=vat_pct,
        )
    )

    per_m2_invalid = baseline.total_m2 <= 0
    scenarios.append(
        _build_scenario(
            mode="PER_M2",
            input_params={"rate_per_m2": str(pricing.rate_per_m2) if pricing.rate_per_m2 is not None else None},
            baseline=baseline,
            price_ex_vat=Decimal(str(pricing.rate_per_m2 or 0)) * baseline.total_m2,
            warnings=["No m² units available for this project"] if per_m2_invalid else [],
            invalid=per_m2_invalid or pricing.rate_per_m2 is None,
            details_lines=[f"total_m2({baseline.total_m2}) × rate_per_m2({pricing.rate_per_m2 or Decimal('0.00')})"],
            vat_pct=vat_pct,
        )
    )

    scenarios.append(
        _build_scenario(
            mode="PER_ROOM",
            input_params={"rate_per_room": str(pricing.rate_per_room) if pricing.rate_per_room is not None else None},
            baseline=baseline,
            price_ex_vat=Decimal(str(pricing.rate_per_room or 0)) * Decimal(str(baseline.rooms_count)),
            warnings=["No rooms available for this project"] if baseline.rooms_count == 0 else [],
            invalid=baseline.rooms_count == 0 or pricing.rate_per_room is None,
            details_lines=[f"rooms_count({baseline.rooms_count}) × rate_per_room({pricing.rate_per_room or Decimal('0.00')})"],
            vat_pct=vat_pct,
        )
    )

    piece_rate = Decimal(str(pricing.rate_per_piece or 0))
    piece_warnings: list[str] = []
    if baseline.items_count == 0:
        piece_warnings.append("No work items available for piecework")
    piece_details = [f"items_count({baseline.items_count}) × rate_per_piece({piece_rate})"]
    if pricing.target_margin_pct is not None:
        margin = Decimal(str(pricing.target_margin_pct)) / Decimal("100")
        if margin < Decimal("1"):
            needed = _quantize_money(
                baseline.internal_total_cost / (Decimal("1") - margin) / Decimal(str(max(baseline.items_count, 1)))
            )
            piece_details.append(
                f"target_margin({pricing.target_margin_pct}%) ⇒ suggested_rate_per_piece({needed})"
            )
    scenarios.append(
        _build_scenario(
            mode="PIECEWORK",
            input_params={
                "rate_per_piece": str(pricing.rate_per_piece) if pricing.rate_per_piece is not None else None,
                "target_margin_pct": str(pricing.target_margin_pct) if pricing.target_margin_pct is not None else None,
            },
            baseline=baseline,
            price_ex_vat=piece_rate * Decimal(str(baseline.items_count)),
            warnings=piece_warnings,
            invalid=baseline.items_count == 0 or pricing.rate_per_piece is None,
            details_lines=piece_details,
            vat_pct=vat_pct,
        )
    )

    return baseline, scenarios


def select_pricing_mode(db: Session, *, pricing: ProjectPricing, mode: str, user_id: str | None) -> ProjectPricing:
    normalized_mode = (mode or "").strip().upper()
    if normalized_mode not in PRICING_MODES:
        raise PricingValidationError({"mode": "Выберите корректный режим"})

    pricing.mode = normalized_mode
    db.add(pricing)
    db.add(
        AuditEvent(
            event_type="pricing_mode_selected",
            user_id=user_id,
            entity_type="project",
            entity_id=pricing.project_id,
            details=json.dumps({"project_id": pricing.project_id, "mode": normalized_mode}, ensure_ascii=False),
        )
    )
    logger.info("event=pricing_mode_selected project_id=%s mode=%s user_id=%s", pricing.project_id, normalized_mode, user_id)
    db.commit()
    db.refresh(pricing)
    return pricing


def update_project_pricing(
    db: Session,
    *,
    pricing: ProjectPricing,
    payload: dict,
    user_id: str | None,
) -> ProjectPricing:
    errors: dict[str, str] = {}
    mode = (payload.get("mode") or "").strip().upper()
    if mode not in PRICING_MODES:
        errors["mode"] = "Выберите корректный режим"

    hourly_rate_override = _parse_decimal(payload.get("hourly_rate_override"), field="hourly_rate_override", errors=errors)
    fixed_total_price = _parse_decimal(payload.get("fixed_total_price"), field="fixed_total_price", errors=errors)
    rate_per_m2 = _parse_decimal(payload.get("rate_per_m2"), field="rate_per_m2", errors=errors)
    rate_per_room = _parse_decimal(payload.get("rate_per_room"), field="rate_per_room", errors=errors)
    rate_per_piece = _parse_decimal(payload.get("rate_per_piece"), field="rate_per_piece", errors=errors)

    target_margin_pct = None
    target_margin_raw = payload.get("target_margin_pct")
    if target_margin_raw not in (None, ""):
        try:
            target_margin_pct = Decimal(target_margin_raw).quantize(Decimal("0.01"))
            if target_margin_pct < 0 or target_margin_pct > 80:
                errors["target_margin_pct"] = "Маржа должна быть в диапазоне 0–80%"
        except (InvalidOperation, TypeError):
            errors["target_margin_pct"] = "Некорректное число"

    if mode == "FIXED_TOTAL" and fixed_total_price is None:
        errors.setdefault("fixed_total_price", "Для Fixed total укажите общую цену")
    if mode == "PER_M2" and rate_per_m2 is None:
        errors.setdefault("rate_per_m2", "Для Per m² укажите ставку")
    if mode == "PER_ROOM" and rate_per_room is None:
        errors.setdefault("rate_per_room", "Для Per room укажите ставку")
    if mode == "PIECEWORK" and rate_per_piece is None:
        errors.setdefault("rate_per_piece", "Для Piecework укажите ставку")

    if errors:
        raise PricingValidationError(errors)

    changed_fields: list[str] = []

    def _set(field: str, value):
        nonlocal changed_fields
        if getattr(pricing, field) != value:
            changed_fields.append(field)
            setattr(pricing, field, value)

    _set("mode", mode)
    _set("hourly_rate_override", hourly_rate_override)
    _set("fixed_total_price", fixed_total_price)
    _set("rate_per_m2", rate_per_m2)
    _set("rate_per_room", rate_per_room)
    _set("rate_per_piece", rate_per_piece)
    _set("target_margin_pct", target_margin_pct)
    _set("include_materials", payload.get("include_materials") in ("on", "true", True, "1", 1))
    _set(
        "include_travel_setup_buffers",
        payload.get("include_travel_setup_buffers") in ("on", "true", True, "1", 1),
    )
    _set("currency", (payload.get("currency") or "SEK").upper())

    db.add(pricing)
    db.add(
        AuditEvent(
            event_type="pricing_updated",
            user_id=user_id,
            entity_type="project",
            entity_id=pricing.project_id,
            details=json.dumps(
                {
                    "project_id": pricing.project_id,
                    "mode": pricing.mode,
                    "changed_fields": changed_fields,
                },
                ensure_ascii=False,
            ),
        )
    )
    logger.info(
        "event=pricing_updated project_id=%s mode=%s changed_fields=%s user_id=%s",
        pricing.project_id,
        pricing.mode,
        ",".join(changed_fields),
        user_id,
    )
    db.commit()
    db.refresh(pricing)
    return pricing
