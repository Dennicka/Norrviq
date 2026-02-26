from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

from sqlalchemy.orm import Session, selectinload

from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.settings import get_or_create_settings

MONEY_Q = Decimal("0.01")
HOURS_Q = Decimal("0.01")
QTY_Q = Decimal("0.01")


class ScopeMode(str, Enum):
    ROOM = "ROOM"
    PROJECT = "PROJECT"
    SELECTED_ROOMS = "SELECTED_ROOMS"
    CUSTOM_QTY = "CUSTOM_QTY"


class BasisType(str, Enum):
    FLOOR_AREA = "floor_area_m2"
    WALL_AREA = "wall_area_m2"
    CEILING_AREA = "ceiling_area_m2"
    PERIMETER = "perimeter_m"
    OPENINGS_COUNT = "openings_count"
    CUSTOM_QTY = "custom_qty"


class PricingMode(str, Enum):
    HOURLY = "HOURLY"
    PER_M2 = "PER_M2"
    FIXED_TOTAL = "FIXED_TOTAL"
    PIECEWORK = "PIECEWORK"


@dataclass
class RoomGeometry:
    room_id: int
    floor_area_m2: Decimal = Decimal("0")
    wall_area_m2: Decimal = Decimal("0")
    ceiling_area_m2: Decimal = Decimal("0")
    perimeter_m: Decimal = Decimal("0")
    openings_count: Decimal = Decimal("0")


@dataclass
class ProjectGeometry:
    rooms: dict[int, RoomGeometry] = field(default_factory=dict)


@dataclass
class Totals:
    total_hours: Decimal
    sell_ex_vat: Decimal
    labour_cost_ex_vat: Decimal
    materials_ex_vat: Decimal
    vat_total: Decimal
    total_ex_vat: Decimal
    total_inc_vat: Decimal
    profit_ex_vat: Decimal
    margin_percent: Decimal
    effective_hourly_ex_vat: Decimal


@dataclass
class RecalcResult:
    totals: Totals


@dataclass
class ProjectEstimate:
    totals: Totals
    per_room_hours: dict[int | None, Decimal]
    per_category_hours: dict[str, Decimal]
    mode_comparison: dict[str, Totals]


@dataclass
class EstimatorTotals:
    total_hours: Decimal
    labour: Decimal
    materials: Decimal
    subtotal: Decimal
    vat: Decimal
    total: Decimal


def _d(value: object | None) -> Decimal:
    return Decimal(str(value or 0))


def _q(value: Decimal, quantum: Decimal = MONEY_Q) -> Decimal:
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def _parse_scope_mode(value: str | None) -> ScopeMode:
    normalized = (value or ScopeMode.ROOM.value).strip()
    aliases = {
        "room": ScopeMode.ROOM,
        "project": ScopeMode.PROJECT,
        "selected_rooms": ScopeMode.SELECTED_ROOMS,
        "custom_qty": ScopeMode.CUSTOM_QTY,
    }
    low = normalized.lower()
    if low in aliases:
        return aliases[low]
    upper = normalized.upper()
    return ScopeMode[upper] if upper in ScopeMode.__members__ else ScopeMode.ROOM


def _parse_pricing_mode(value: str | None) -> PricingMode:
    normalized = (value or PricingMode.HOURLY.value).strip().upper()
    aliases = {"hourly": PricingMode.HOURLY, "sqm": PricingMode.PER_M2, "per_m2": PricingMode.PER_M2, "fixed": PricingMode.FIXED_TOTAL, "piecework": PricingMode.PIECEWORK}
    if value and value.lower() in aliases:
        return aliases[value.lower()]
    if normalized in PricingMode.__members__:
        return PricingMode[normalized]
    return PricingMode.HOURLY


def _parse_basis_type(value: str | None) -> BasisType:
    normalized = (value or BasisType.FLOOR_AREA.value).strip().lower()
    for basis in BasisType:
        if basis.value == normalized:
            return basis
    return BasisType.FLOOR_AREA


def _selected_room_ids(item: ProjectWorkItem) -> list[int]:
    if not item.selected_room_ids_json:
        return []
    try:
        raw = json.loads(item.selected_room_ids_json)
        return [int(v) for v in raw if str(v).isdigit()]
    except (ValueError, TypeError, json.JSONDecodeError):
        return []


def aggregate_project_geometry(db: Session, project_id: int) -> ProjectGeometry:
    rows = db.query(Room).filter(Room.project_id == project_id).all()
    rooms: dict[int, RoomGeometry] = {}
    for room in rows:
        rooms[room.id] = RoomGeometry(
            room_id=room.id,
            floor_area_m2=_q(_d(room.floor_area_m2), QTY_Q),
            wall_area_m2=_q(_d(room.wall_area_m2), QTY_Q),
            ceiling_area_m2=_q(_d(room.ceiling_area_m2), QTY_Q),
            perimeter_m=_q(_d(room.wall_perimeter_m), QTY_Q),
            openings_count=Decimal("0"),
        )
    return ProjectGeometry(rooms=rooms)


def _room_basis_value(room_geometry: RoomGeometry, basis: BasisType) -> Decimal:
    mapping = {
        BasisType.FLOOR_AREA: room_geometry.floor_area_m2,
        BasisType.WALL_AREA: room_geometry.wall_area_m2,
        BasisType.CEILING_AREA: room_geometry.ceiling_area_m2,
        BasisType.PERIMETER: room_geometry.perimeter_m,
        BasisType.OPENINGS_COUNT: room_geometry.openings_count,
    }
    return mapping.get(basis, Decimal("0"))


def compute_work_item_qty(item: ProjectWorkItem, rooms: dict[int, RoomGeometry], project_geometry: ProjectGeometry) -> Decimal:
    scope = _parse_scope_mode(getattr(item, "scope_mode", None))
    basis = _parse_basis_type(getattr(item, "basis_type", None))
    if scope == ScopeMode.CUSTOM_QTY or basis == BasisType.CUSTOM_QTY:
        return _q(_d(getattr(item, "manual_qty", None) or getattr(item, "quantity", None)), QTY_Q)

    # Backward-compatible behavior for existing work items created with explicit quantity/layers.
    persisted_qty = _d(getattr(item, "quantity", None))
    raw_scope_value = (getattr(item, "scope_mode", None) or "").strip()
    raw_scope = raw_scope_value.lower()
    is_legacy_scope_value = raw_scope_value == raw_scope and raw_scope in {"room", "project", "selected_rooms", "custom_qty", "all_rooms"}
    if persisted_qty > 0 and getattr(item, "manual_qty", None) is None:
        if is_legacy_scope_value and getattr(item, "basis_type", None) in {None, "", BasisType.FLOOR_AREA.value}:
            return _q(persisted_qty, QTY_Q)

    if scope == ScopeMode.ROOM:
        room_geometry = rooms.get(item.room_id) if item.room_id is not None else None
        return _q(_room_basis_value(room_geometry, basis), QTY_Q) if room_geometry else Decimal("0.00")

    if scope == ScopeMode.SELECTED_ROOMS:
        ids = _selected_room_ids(item)
        return _q(sum((_room_basis_value(rooms[rid], basis) for rid in ids if rid in rooms), Decimal("0")), QTY_Q)

    return _q(sum((_room_basis_value(room_geometry, basis) for room_geometry in project_geometry.rooms.values()), Decimal("0")), QTY_Q)


def compute_work_item_hours(item: ProjectWorkItem, qty: Decimal, speed_profile: object | None = None) -> Decimal:
    del speed_profile
    norm_hours = getattr(item, "norm_hours_per_unit", None)
    if norm_hours is not None:
        return _q(qty * _d(norm_hours), HOURS_Q)

    wt = getattr(item, "work_type", None)
    hours_per_unit = _d(getattr(wt, "hours_per_unit", None))
    difficulty = _d(getattr(item, "difficulty_factor", None) or 1)
    base_hours = _q(qty * hours_per_unit, HOURS_Q)
    return _q(base_hours * difficulty, HOURS_Q)


def compute_work_item_sell(item: ProjectWorkItem, qty: Decimal, hours: Decimal, settings: object, mode_override: PricingMode | None = None) -> Decimal:
    mode = mode_override or _parse_pricing_mode(getattr(item, "pricing_mode", None))
    if mode == PricingMode.FIXED_TOTAL:
        return _q(_d(getattr(item, "fixed_total_ex_vat", None) or getattr(item, "fixed_price_sek", None)))
    if mode == PricingMode.HOURLY:
        rate = _d(getattr(item, "hourly_rate_ex_vat", None) or getattr(item, "hourly_rate_sek", None) or getattr(settings, "hourly_rate_company", None))
        return _q(hours * rate)
    unit_rate = _d(getattr(item, "unit_rate_ex_vat", None) or getattr(item, "area_rate_sek", None))
    return _q(qty * unit_rate)


def _totals_from_rows(rows: list[dict], vat_percent: Decimal) -> Totals:
    total_hours = _q(sum((row["hours"] for row in rows), Decimal("0")), HOURS_Q)
    sell = _q(sum((row["sell"] for row in rows), Decimal("0")))
    labour = _q(sum((row["labour"] for row in rows), Decimal("0")))
    materials = _q(sum((row["materials"] for row in rows), Decimal("0")))
    total_ex_vat = _q(sell + materials)
    vat_total = _q(total_ex_vat * (vat_percent / Decimal("100")))
    total_inc_vat = _q(total_ex_vat + vat_total)
    profit = _q(sell - labour - materials)
    margin = Decimal("0.00") if sell <= 0 else _q((profit / sell) * Decimal("100"))
    effective_hourly = Decimal("0.00") if total_hours <= 0 else _q(sell / total_hours)
    return Totals(
        total_hours=total_hours,
        sell_ex_vat=sell,
        labour_cost_ex_vat=labour,
        materials_ex_vat=materials,
        vat_total=vat_total,
        total_ex_vat=total_ex_vat,
        total_inc_vat=total_inc_vat,
        profit_ex_vat=profit,
        margin_percent=margin,
        effective_hourly_ex_vat=effective_hourly,
    )


def _load_project(db: Session, project_id: int) -> Project:
    project = (
        db.query(Project)
        .options(selectinload(Project.work_items).selectinload(ProjectWorkItem.work_type), selectinload(Project.rooms), selectinload(Project.pricing))
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise ValueError("Project not found")
    return project


def calculate_project_pricing_totals(db: Session, project_id: int, mode: str) -> Totals:
    project = _load_project(db, project_id)
    settings = get_or_create_settings(db)
    geometry = aggregate_project_geometry(db, project_id)
    rows: list[dict] = []
    labour_rate = _d(getattr(settings, "internal_labor_cost_rate_sek", None))
    for item in project.work_items:
        qty = compute_work_item_qty(item, geometry.rooms, geometry)
        hours = compute_work_item_hours(item, qty)
        sell = compute_work_item_sell(item, qty, hours, settings, mode_override=_parse_pricing_mode(mode))
        rows.append({"hours": hours, "sell": sell, "labour": _q(hours * labour_rate), "materials": _q(_d(item.materials_cost_sek))})
    return _totals_from_rows(rows, _d(getattr(settings, "moms_percent", 0)))


def recalculate_project_work_items(db: Session, project_id: int) -> RecalcResult:
    project = _load_project(db, project_id)
    settings = get_or_create_settings(db)
    geometry = aggregate_project_geometry(db, project_id)
    rows: list[dict] = []
    labour_rate = _d(getattr(settings, "internal_labor_cost_rate_sek", None))

    for item in project.work_items:
        qty = compute_work_item_qty(item, geometry.rooms, geometry)
        hours = compute_work_item_hours(item, qty)
        sell = compute_work_item_sell(item, qty, hours, settings)
        labour = _q(hours * labour_rate)
        item.calculated_qty = qty
        item.calculated_hours = hours
        item.calculated_sell_ex_vat = sell
        item.calculated_labour_cost_ex_vat = labour
        item.calculated_cost_without_moms = sell
        item.labor_cost_sek = labour
        rows.append({"hours": hours, "sell": sell, "labour": labour, "materials": _q(_d(item.materials_cost_sek))})

    totals = _totals_from_rows(rows, _d(getattr(settings, "moms_percent", 0)))
    db.commit()
    return RecalcResult(totals=totals)


def build_project_estimate(db: Session, project_id: int) -> ProjectEstimate:
    project = _load_project(db, project_id)
    settings = get_or_create_settings(db)
    geometry = aggregate_project_geometry(db, project_id)
    labour_rate = _d(getattr(settings, "internal_labor_cost_rate_sek", None))
    rows: list[dict] = []
    per_room_hours: dict[int | None, Decimal] = {}
    per_category_hours: dict[str, Decimal] = {}

    for item in project.work_items:
        qty = compute_work_item_qty(item, geometry.rooms, geometry)
        hours = compute_work_item_hours(item, qty)
        sell = compute_work_item_sell(item, qty, hours, settings)
        labour = _q(hours * labour_rate)
        materials = _q(_d(item.materials_cost_sek))
        rows.append({"hours": hours, "sell": sell, "labour": labour, "materials": materials})
        per_room_hours[item.room_id] = _q(per_room_hours.get(item.room_id, Decimal("0")) + hours, HOURS_Q)
        category = (item.work_type.category if item.work_type else "other") or "other"
        per_category_hours[category] = _q(per_category_hours.get(category, Decimal("0")) + hours, HOURS_Q)

    modes = [PricingMode.HOURLY.value, PricingMode.PER_M2.value, PricingMode.FIXED_TOTAL.value, PricingMode.PIECEWORK.value]
    comparison = {mode: calculate_project_pricing_totals(db, project_id, mode) for mode in modes}
    totals = _totals_from_rows(rows, _d(getattr(settings, "moms_percent", 0)))
    return ProjectEstimate(totals=totals, per_room_hours=per_room_hours, per_category_hours=per_category_hours, mode_comparison=comparison)


def compute_estimator_totals(*, project: Project, materials_ex_vat: Decimal, vat_percent: Decimal) -> EstimatorTotals:
    total_hours = _q(sum((Decimal(str(item.calculated_hours or 0)) for item in project.work_items), Decimal("0")), HOURS_Q)
    labour = _q(sum((Decimal(str(item.calculated_cost_without_moms or item.calculated_sell_ex_vat or 0)) for item in project.work_items), Decimal("0")))
    materials = _q(Decimal(str(materials_ex_vat or 0)))
    subtotal = _q(labour + materials)
    vat = _q(subtotal * (Decimal(str(vat_percent or 0)) / Decimal("100")))
    return EstimatorTotals(total_hours=total_hours, labour=labour, materials=materials, subtotal=subtotal, vat=vat, total=_q(subtotal + vat))
