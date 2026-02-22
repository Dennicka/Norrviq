import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session, selectinload

from app.models.audit_event import AuditEvent
from app.models.buffer_rule import BufferRule
from app.models.cost import ProjectCostItem
from app.models.project import Project, ProjectWorkItem, ProjectWorkerAssignment
from app.models.project_buffer_settings import ProjectBufferSettings
from app.models.project_execution_profile import ProjectExecutionProfile
from app.models.speed_profile import SpeedProfile
from app.models.project_pricing import ProjectPricing
from app.models.pricing_policy import PricingPolicy
from app.models.settings import get_or_create_settings
from app.services.buffer_rules import resolve_effective_buffer
from app.services.takeoff import compute_project_areas, get_or_create_project_takeoff_settings

logger = logging.getLogger("uvicorn.error")

PRICING_MODES = {"HOURLY", "FIXED_TOTAL", "PER_M2", "PER_ROOM", "PIECEWORK"}
DEFAULT_VAT_PCT = Decimal("25.00")
HOURS_QUANT = Decimal("0.01")
MONEY_QUANT = Decimal("0.01")
LOW_MARGIN_WARN_PCT = Decimal("10.0")

WARNING_MISSING_UNITS_M2 = "MISSING_UNITS_M2"
WARNING_MISSING_UNITS_ROOMS = "MISSING_UNITS_ROOMS"
WARNING_MISSING_ITEMS = "MISSING_ITEMS"
WARNING_MISSING_BASELINE = "MISSING_BASELINE"
WARNING_NEGATIVE_MARGIN = "NEGATIVE_MARGIN"
WARNING_LOW_MARGIN = "LOW_MARGIN"
WARNING_INVALID_TARGET_MARGIN = "INVALID_TARGET_MARGIN"
WARNING_MISSING_PERIMETER_HEIGHT = "MISSING_PERIMETER_HEIGHT"

FLOOR_REASON_MARGIN_BELOW_MIN = "MARGIN_BELOW_MIN"
FLOOR_REASON_PROFIT_BELOW_MIN = "PROFIT_BELOW_MIN"
FLOOR_REASON_EFFECTIVE_HOURLY_BELOW_MIN = "EFFECTIVE_HOURLY_BELOW_MIN"
FLOOR_REASON_NEGATIVE_PROFIT = "NEGATIVE_PROFIT"


@dataclass
class FloorReason:
    code: str
    text: str


@dataclass
class FloorResult:
    is_below_floor: bool
    reasons: list[FloorReason]
    recommended_min_price_ex_vat: Decimal
    recommended_rate_per_m2: Decimal | None
    recommended_rate_per_room: Decimal | None
    recommended_rate_per_piece: Decimal | None
    recommended_fixed_total: Decimal

@dataclass
class ProjectBaseline:
    raw_labor_hours_total: Decimal
    speed_profile_code: str
    speed_multiplier: Decimal
    speed_hours_delta: Decimal
    labor_hours_after_speed: Decimal
    raw_internal_cost: Decimal
    labor_hours_total: Decimal
    labor_cost_internal: Decimal
    materials_cost_internal: Decimal
    travel_setup_cost_internal: Decimal
    overhead_cost_internal: Decimal
    internal_total_cost: Decimal
    total_m2: Decimal
    m2_basis: str
    total_floor_m2: Decimal
    total_ceiling_m2: Decimal
    total_wall_m2: Decimal
    total_paintable_m2: Decimal
    rooms_count: int
    items_count: int
    buffers_hours_total: Decimal
    buffers_cost_total: Decimal
    buffers: list[dict]
    effective_buffer: dict | None = None


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


@dataclass
class DesiredInput:
    desired_effective_hourly_ex_vat: Decimal | None = None
    desired_margin_pct: Decimal | None = None
    rate_per_m2: Decimal | None = None
    rate_per_room: Decimal | None = None
    rate_per_piece: Decimal | None = None
    fixed_total_price: Decimal | None = None


@dataclass
class ConversionEstimate:
    mode: str
    price_ex_vat: Decimal
    effective_hourly_ex_vat: Decimal | None
    profit: Decimal
    margin_pct: Decimal | None
    warnings: list[str]


@dataclass
class ConversionResult:
    base_price_ex_vat: Decimal
    implied_fixed_total_price: Decimal
    implied_rate_per_m2: Decimal | None
    implied_rate_per_room: Decimal | None
    implied_rate_per_piece: Decimal | None
    effective_hourly_ex_vat: Decimal | None
    profit: Decimal
    margin_pct: Decimal | None
    mode_results: dict[str, ConversionEstimate]
    warnings: list[str]


class PricingValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("Pricing validation failed")
        self.errors = errors


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT)


def _quantize_hours(value: Decimal) -> Decimal:
    return value.quantize(HOURS_QUANT)


def _quantize_margin(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.1"))


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


def get_or_create_project_execution_profile(db: Session, project_id: int) -> ProjectExecutionProfile:
    profile = db.query(ProjectExecutionProfile).filter(ProjectExecutionProfile.project_id == project_id).first()
    if profile:
        return profile
    profile = ProjectExecutionProfile(project_id=project_id, apply_scope="PROJECT")
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def get_or_create_project_buffer_settings(db: Session, project_id: int) -> ProjectBufferSettings:
    settings = db.query(ProjectBufferSettings).filter(ProjectBufferSettings.project_id == project_id).first()
    if settings:
        return settings
    settings = ProjectBufferSettings(project_id=project_id)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


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




def get_medium_speed_profile(db: Session) -> SpeedProfile:
    profile = db.query(SpeedProfile).filter(SpeedProfile.code == "MEDIUM").first()
    if profile:
        return profile
    profile = SpeedProfile(code="MEDIUM", name_ru="Средне", name_sv="Normal", multiplier=Decimal("1.000"), is_active=True)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def resolve_project_speed_profile(db: Session, project: Project) -> SpeedProfile:
    execution = db.query(ProjectExecutionProfile).filter(ProjectExecutionProfile.project_id == project.id).first()
    if execution and execution.speed_profile_id:
        profile = db.get(SpeedProfile, execution.speed_profile_id)
        if profile and profile.is_active:
            return profile
    return get_medium_speed_profile(db)
def compute_project_baseline(
    db: Session,
    project_id: int,
    *,
    include_materials: bool,
    include_travel_setup_buffers: bool,
    request_id: str | None = None,
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

    estimated_hours_raw = sum((Decimal(str(item.calculated_hours or 0)) for item in project.work_items), Decimal("0"))
    raw_labor_hours_total = _quantize_hours(estimated_hours_raw)
    speed_profile = resolve_project_speed_profile(db, project)
    speed_multiplier = Decimal(str(speed_profile.multiplier or 1))
    labor_hours_after_speed = _quantize_hours(raw_labor_hours_total * speed_multiplier)
    speed_hours_delta = _quantize_hours(labor_hours_after_speed - raw_labor_hours_total)
    labor_hours_total = labor_hours_after_speed

    weighted_hours = Decimal("0")
    weighted_rate_cost = Decimal("0")
    for assignment in project.worker_assignments:
        hours = Decimal(str(assignment.actual_hours if assignment.actual_hours not in (None, 0) else assignment.planned_hours or 0))
        if hours <= 0:
            continue
        worker_rate = assignment.worker.hourly_rate if assignment.worker else None
        hourly_rate = Decimal(str(worker_rate if worker_rate is not None else default_worker_rate))
        if hourly_rate <= 0:
            continue
        weighted_hours += hours
        weighted_rate_cost += hours * hourly_rate

    internal_hourly_rate = default_worker_rate
    if weighted_hours > 0:
        internal_hourly_rate = weighted_rate_cost / weighted_hours

    salary_fund = labor_hours_after_speed * internal_hourly_rate
    labor_cost_internal = _quantize_money(salary_fund * (Decimal("1") + employer_pct))
    if labor_hours_after_speed > 0 and internal_hourly_rate > 0 and labor_cost_internal <= 0:
        raise ValueError("Invalid labor baseline: non-zero hours and rate must produce positive labor_cost_internal")

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

    raw_internal_cost = _quantize_money(
        labor_cost_internal
        + materials_cost_internal
        + travel_setup_cost_internal
        + _quantize_money(other_cost_internal)
        + overhead_cost_internal
    )
    internal_total_cost = raw_internal_cost

    project_buffer_settings = (
        db.query(ProjectBufferSettings).filter(ProjectBufferSettings.project_id == project_id).first()
    )
    include_setup_cleanup_travel = include_travel_setup_buffers
    include_risk = True
    if project_buffer_settings:
        include_setup_cleanup_travel = project_buffer_settings.include_setup_cleanup_travel
        include_risk = project_buffer_settings.include_risk

    fixed_hours = Decimal("0")
    percent_hours = Decimal("0")
    fixed_cost = Decimal("0")
    percent_cost = Decimal("0")
    breakdown: list[dict] = []
    effective = resolve_effective_buffer(db, project_id)
    effective_meta: dict | None = None
    if effective.applied_rule_id is not None:
        rule = db.get(BufferRule, effective.applied_rule_id)
    else:
        rule = None

    if rule is not None:
        if rule.kind in {"SETUP", "CLEANUP", "TRAVEL"} and not include_setup_cleanup_travel:
            effective_meta = {"rule_id": rule.id, "applied": False, "reason": "rule disabled by project setup/cleanup/travel flag"}
        elif rule.kind == "RISK" and not include_risk:
            effective_meta = {"rule_id": rule.id, "applied": False, "reason": "rule disabled by project risk flag"}
        else:
            value = Decimal(str(rule.value or 0))
            base = labor_hours_after_speed if rule.basis == "LABOR_HOURS" else raw_internal_cost
            delta = Decimal("0")
            if rule.unit == "PERCENT":
                delta = base * (value / Decimal("100"))
                if rule.basis == "LABOR_HOURS":
                    percent_hours += delta
                else:
                    percent_cost += delta
            elif rule.unit == "FIXED_HOURS" and rule.basis == "LABOR_HOURS":
                delta = value
                fixed_hours += delta
            elif rule.unit == "FIXED_SEK" and rule.basis == "INTERNAL_COST":
                delta = value
                fixed_cost += delta

            breakdown.append(
                {
                    "rule_id": rule.id,
                    "kind": rule.kind,
                    "basis": rule.basis,
                    "unit": rule.unit,
                    "scope_type": rule.scope_type,
                    "scope_id": rule.scope_id,
                    "priority": rule.priority,
                    "hours_delta": _quantize_hours(delta) if rule.basis == "LABOR_HOURS" else Decimal("0.00"),
                    "sek_delta": _quantize_money(delta) if rule.basis == "INTERNAL_COST" else Decimal("0.00"),
                    "reason": effective.reason,
                }
            )
            effective_meta = {
                "rule_id": rule.id,
                "scope": effective.scope,
                "basis": effective.buffer_basis,
                "unit": effective.buffer_unit,
                "value": str(effective.buffer_value) if effective.buffer_value is not None else None,
                "applied": True,
                "reason": effective.reason,
            }
    elif effective.applied_rule_id is None:
        effective_meta = {"rule_id": None, "applied": False, "reason": effective.reason}

    buffers_hours_total = _quantize_hours(fixed_hours + percent_hours)
    buffers_cost_total = _quantize_money(fixed_cost + percent_cost)
    labor_hours_total = _quantize_hours(labor_hours_after_speed + buffers_hours_total)
    internal_total_cost = _quantize_money(raw_internal_cost + buffers_cost_total)

    logger.info(
        "event=baseline_recomputed project_id=%s request_id=%s raw_hours=%s speed_multiplier=%s speed_hours=%s raw_cost=%s buffer_hours=%s buffer_cost=%s",
        project_id,
        request_id or "-",
        raw_labor_hours_total,
        speed_multiplier,
        labor_hours_after_speed,
        raw_internal_cost,
        buffers_hours_total,
        buffers_cost_total,
    )

    takeoff_settings = get_or_create_project_takeoff_settings(db, project_id)
    areas = compute_project_areas(db, project_id)
    total_m2 = areas.total_by_basis(takeoff_settings.m2_basis)
    rooms_count = len(project.rooms)
    items_count = len(project.work_items)

    return ProjectBaseline(
        raw_labor_hours_total=raw_labor_hours_total,
        speed_profile_code=speed_profile.code,
        speed_multiplier=speed_multiplier,
        speed_hours_delta=speed_hours_delta,
        labor_hours_after_speed=labor_hours_after_speed,
        raw_internal_cost=raw_internal_cost,
        labor_hours_total=labor_hours_total,
        labor_cost_internal=labor_cost_internal,
        materials_cost_internal=materials_cost_internal,
        travel_setup_cost_internal=travel_setup_cost_internal,
        overhead_cost_internal=overhead_cost_internal,
        internal_total_cost=internal_total_cost,
        total_m2=total_m2,
        m2_basis=takeoff_settings.m2_basis,
        total_floor_m2=areas.total_floor_m2,
        total_ceiling_m2=areas.total_ceiling_m2,
        total_wall_m2=areas.total_wall_m2,
        total_paintable_m2=areas.total_paintable_m2,
        rooms_count=rooms_count,
        items_count=items_count,
        buffers_hours_total=buffers_hours_total,
        buffers_cost_total=buffers_cost_total,
        buffers=breakdown,
        effective_buffer=effective_meta,
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
    warning_codes = list(warnings)
    if baseline.labor_hours_total <= 0:
        warning_codes.append(WARNING_MISSING_BASELINE)
    if profit < 0:
        warning_codes.append(WARNING_NEGATIVE_MARGIN)
    elif margin_pct is not None and margin_pct < LOW_MARGIN_WARN_PCT:
        warning_codes.append(WARNING_LOW_MARGIN)

    return PricingScenario(
        mode=mode,
        input_params=input_params,
        price_ex_vat=price_ex_vat,
        vat_amount=vat_amount,
        price_inc_vat=price_inc_vat,
        effective_hourly_sell_rate=effective_hourly_sell_rate,
        profit=profit,
        margin_pct=margin_pct,
        warnings=warning_codes,
        invalid=invalid,
        details_lines=details_lines,
    )


def compute_pricing_scenarios(db: Session, project_id: int, *, request_id: str | None = None) -> tuple[ProjectBaseline, list[PricingScenario]]:
    pricing = get_or_create_project_pricing(db, project_id)
    baseline = compute_project_baseline(
        db,
        project_id,
        include_materials=pricing.include_materials,
        include_travel_setup_buffers=pricing.include_travel_setup_buffers,
        request_id=request_id,
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

    per_m2_needs_walls = baseline.m2_basis in {"WALL_AREA", "PAINTABLE_TOTAL"}
    per_m2_missing_dims = per_m2_needs_walls and baseline.total_wall_m2 <= 0
    per_m2_invalid = baseline.total_m2 <= 0 or per_m2_missing_dims
    scenarios.append(
        _build_scenario(
            mode="PER_M2",
            input_params={"rate_per_m2": str(pricing.rate_per_m2) if pricing.rate_per_m2 is not None else None},
            baseline=baseline,
            price_ex_vat=Decimal(str(pricing.rate_per_m2 or 0)) * baseline.total_m2,
            warnings=([WARNING_MISSING_UNITS_M2] + ([WARNING_MISSING_PERIMETER_HEIGHT] if per_m2_missing_dims else [])) if per_m2_invalid else [],
            invalid=per_m2_invalid or pricing.rate_per_m2 is None,
            details_lines=[f"basis({baseline.m2_basis}) total_m2({baseline.total_m2}) × rate_per_m2({pricing.rate_per_m2 or Decimal('0.00')})"],
            vat_pct=vat_pct,
        )
    )

    scenarios.append(
        _build_scenario(
            mode="PER_ROOM",
            input_params={"rate_per_room": str(pricing.rate_per_room) if pricing.rate_per_room is not None else None},
            baseline=baseline,
            price_ex_vat=Decimal(str(pricing.rate_per_room or 0)) * Decimal(str(baseline.rooms_count)),
            warnings=[WARNING_MISSING_UNITS_ROOMS] if baseline.rooms_count == 0 else [],
            invalid=baseline.rooms_count == 0 or pricing.rate_per_room is None,
            details_lines=[f"rooms_count({baseline.rooms_count}) × rate_per_room({pricing.rate_per_room or Decimal('0.00')})"],
            vat_pct=vat_pct,
        )
    )

    piece_rate = Decimal(str(pricing.rate_per_piece or 0))
    piece_warnings: list[str] = []
    if baseline.items_count == 0:
        piece_warnings.append(WARNING_MISSING_ITEMS)
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


def compute_conversions(db: Session, project_id: int, desired: DesiredInput) -> ConversionResult:
    pricing = get_or_create_project_pricing(db, project_id)
    baseline = compute_project_baseline(
        db,
        project_id,
        include_materials=pricing.include_materials,
        include_travel_setup_buffers=pricing.include_travel_setup_buffers,
    )

    warnings: list[str] = []
    price_ex_vat = Decimal("0")

    if desired.desired_effective_hourly_ex_vat is not None:
        price_ex_vat = desired.desired_effective_hourly_ex_vat * baseline.labor_hours_total
    elif desired.desired_margin_pct is not None:
        margin_pct = desired.desired_margin_pct
        if margin_pct >= Decimal("100"):
            warnings.append(WARNING_INVALID_TARGET_MARGIN)
        else:
            price_ex_vat = baseline.internal_total_cost / (Decimal("1") - margin_pct / Decimal("100"))
    elif desired.fixed_total_price is not None:
        price_ex_vat = desired.fixed_total_price
    elif desired.rate_per_m2 is not None:
        price_ex_vat = desired.rate_per_m2 * baseline.total_m2
    elif desired.rate_per_room is not None:
        price_ex_vat = desired.rate_per_room * Decimal(str(baseline.rooms_count))
    elif desired.rate_per_piece is not None:
        price_ex_vat = desired.rate_per_piece * Decimal(str(baseline.items_count))

    price_ex_vat = _quantize_money(price_ex_vat)
    if baseline.total_m2 <= 0:
        warnings.append(WARNING_MISSING_UNITS_M2)
    if baseline.rooms_count <= 0:
        warnings.append(WARNING_MISSING_UNITS_ROOMS)
    if baseline.items_count <= 0:
        warnings.append(WARNING_MISSING_ITEMS)
    if baseline.labor_hours_total <= 0:
        warnings.append(WARNING_MISSING_BASELINE)

    implied_rate_per_m2 = None
    if baseline.total_m2 > 0:
        implied_rate_per_m2 = _quantize_money(price_ex_vat / baseline.total_m2)

    implied_rate_per_room = None
    if baseline.rooms_count > 0:
        implied_rate_per_room = _quantize_money(price_ex_vat / Decimal(str(baseline.rooms_count)))

    implied_rate_per_piece = None
    if baseline.items_count > 0:
        implied_rate_per_piece = _quantize_money(price_ex_vat / Decimal(str(baseline.items_count)))

    effective_hourly_ex_vat = None
    if baseline.labor_hours_total > 0:
        effective_hourly_ex_vat = _quantize_money(price_ex_vat / baseline.labor_hours_total)

    profit = _quantize_money(price_ex_vat - baseline.internal_total_cost)
    margin_pct = None
    if price_ex_vat > 0:
        margin_pct = _quantize_margin(profit / price_ex_vat * Decimal("100"))

    mode_results: dict[str, ConversionEstimate] = {}
    for mode in ("FIXED_TOTAL", "PER_M2", "PER_ROOM", "PIECEWORK"):
        mode_warnings = list(warnings)
        mode_price = price_ex_vat
        if mode == "PER_M2" and implied_rate_per_m2 is None:
            mode_price = Decimal("0")
        if mode == "PER_ROOM" and implied_rate_per_room is None:
            mode_price = Decimal("0")
        if mode == "PIECEWORK" and implied_rate_per_piece is None:
            mode_price = Decimal("0")
        mode_effective_hourly = None
        if baseline.labor_hours_total > 0:
            mode_effective_hourly = _quantize_money(mode_price / baseline.labor_hours_total)
        mode_profit = _quantize_money(mode_price - baseline.internal_total_cost)
        mode_margin = None
        if mode_price > 0:
            mode_margin = _quantize_margin(mode_profit / mode_price * Decimal("100"))
        mode_results[mode] = ConversionEstimate(
            mode=mode,
            price_ex_vat=mode_price,
            effective_hourly_ex_vat=mode_effective_hourly,
            profit=mode_profit,
            margin_pct=mode_margin,
            warnings=mode_warnings,
        )

    return ConversionResult(
        base_price_ex_vat=price_ex_vat,
        implied_fixed_total_price=price_ex_vat,
        implied_rate_per_m2=implied_rate_per_m2,
        implied_rate_per_room=implied_rate_per_room,
        implied_rate_per_piece=implied_rate_per_piece,
        effective_hourly_ex_vat=effective_hourly_ex_vat,
        profit=profit,
        margin_pct=margin_pct,
        mode_results=mode_results,
        warnings=list(dict.fromkeys(warnings)),
    )



def _floor_reason_text(code: str, policy: PricingPolicy) -> str:
    if code == FLOOR_REASON_MARGIN_BELOW_MIN:
        return f"Маржа ниже минимума {Decimal(str(policy.min_margin_pct)).quantize(Decimal('0.01'))}%"
    if code == FLOOR_REASON_PROFIT_BELOW_MIN:
        return f"Прибыль ниже минимума {Decimal(str(policy.min_profit_sek)).quantize(Decimal('0.01'))} SEK"
    if code == FLOOR_REASON_EFFECTIVE_HOURLY_BELOW_MIN:
        return f"Эффективная ставка ниже минимума {Decimal(str(policy.min_effective_hourly_ex_vat)).quantize(Decimal('0.01'))} SEK/ч"
    if code == FLOOR_REASON_NEGATIVE_PROFIT:
        return "Отрицательная прибыль"
    return code


def evaluate_floor(baseline: ProjectBaseline, scenario: PricingScenario, policy: PricingPolicy) -> FloorResult:
    min_margin_pct = Decimal(str(policy.min_margin_pct or 0))
    min_profit_sek = Decimal(str(policy.min_profit_sek or 0))
    min_hourly = Decimal(str(policy.min_effective_hourly_ex_vat or 0))

    reasons: list[str] = []
    if scenario.profit < 0:
        reasons.append(FLOOR_REASON_NEGATIVE_PROFIT)
    if scenario.margin_pct is None or scenario.margin_pct < min_margin_pct:
        reasons.append(FLOOR_REASON_MARGIN_BELOW_MIN)
    if scenario.profit < min_profit_sek:
        reasons.append(FLOOR_REASON_PROFIT_BELOW_MIN)
    if scenario.effective_hourly_sell_rate is None or scenario.effective_hourly_sell_rate < min_hourly:
        reasons.append(FLOOR_REASON_EFFECTIVE_HOURLY_BELOW_MIN)

    margin_constraint = Decimal('0')
    if min_margin_pct < Decimal('100'):
        margin_constraint = _quantize_money(baseline.internal_total_cost / (Decimal('1') - min_margin_pct / Decimal('100')))
    hourly_constraint = Decimal('0')
    if baseline.labor_hours_total > 0:
        hourly_constraint = _quantize_money(min_hourly * baseline.labor_hours_total)
    profit_constraint = _quantize_money(baseline.internal_total_cost + min_profit_sek)

    recommended_min_price = max(profit_constraint, margin_constraint, hourly_constraint)

    recommended_rate_per_m2 = None
    if baseline.total_m2 > 0:
        recommended_rate_per_m2 = _quantize_money(recommended_min_price / baseline.total_m2)

    recommended_rate_per_room = None
    if baseline.rooms_count > 0:
        recommended_rate_per_room = _quantize_money(recommended_min_price / Decimal(str(baseline.rooms_count)))

    recommended_rate_per_piece = None
    if baseline.items_count > 0:
        recommended_rate_per_piece = _quantize_money(recommended_min_price / Decimal(str(baseline.items_count)))

    return FloorResult(
        is_below_floor=bool(reasons),
        reasons=[FloorReason(code=code, text=_floor_reason_text(code, policy)) for code in dict.fromkeys(reasons)],
        recommended_min_price_ex_vat=_quantize_money(recommended_min_price),
        recommended_rate_per_m2=recommended_rate_per_m2,
        recommended_rate_per_room=recommended_rate_per_room,
        recommended_rate_per_piece=recommended_rate_per_piece,
        recommended_fixed_total=_quantize_money(recommended_min_price),
    )


def select_pricing_mode(db: Session, *, pricing: ProjectPricing, mode: str, user_id: str | None) -> ProjectPricing:
    normalized_mode = (mode or "").strip().upper()
    if normalized_mode not in PRICING_MODES:
        raise PricingValidationError({"mode": "Выберите корректный режим"})

    if normalized_mode == "HOURLY" and pricing.hourly_rate_override is None:
        settings = get_or_create_settings(db)
        if settings.hourly_rate_company is not None:
            pricing.hourly_rate_override = Decimal(str(settings.hourly_rate_company)).quantize(MONEY_QUANT)
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
