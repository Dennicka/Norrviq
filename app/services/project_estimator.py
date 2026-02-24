from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.services.estimates import WorkItemPricingMode
from app.services.geometry import GeometryValidationError, compute_room_geometry_from_model


MONEY = Decimal("0.01")


@dataclass
class ProjectScope:
    rooms: list[Room]
    room_ids: set[int]
    all_rooms_selected: bool


@dataclass
class LabourTotals:
    total_hours: Decimal
    by_category: dict[str, Decimal]
    hourly_labor_cost: Decimal


@dataclass
class GeometryTotals:
    floors_m2: Decimal
    ceilings_m2: Decimal
    walls_m2: Decimal
    perimeter_m: Decimal
    rooms_count: int


@dataclass
class ProjectEstimateSummary:
    scope: ProjectScope
    geometry: GeometryTotals
    labour: LabourTotals
    total_price: Decimal
    materials_cost: Decimal
    estimate_total: Decimal
    has_missing_data: bool
    pricing_mode: str
    room_rows: list["RoomEstimateRow"] = field(default_factory=list)
    scoped_work_items: list[ProjectWorkItem] = field(default_factory=list)


@dataclass
class RoomEstimateRow:
    room_id: int
    room_name: str
    floor_area_m2: Decimal | None
    wall_area_m2: Decimal | None
    ceiling_area_m2: Decimal | None
    hours: Decimal
    labour_cost: Decimal
    materials_cost: Decimal
    total: Decimal
    has_missing_geometry: bool = False


def _q(value: Decimal) -> Decimal:
    return value.quantize(MONEY)


def _matches_scope(item: ProjectWorkItem, scope: ProjectScope) -> bool:
    if not scope.room_ids:
        return False
    if item.room_id is None:
        return scope.all_rooms_selected
    return item.room_id in scope.room_ids


def build_scope(project: Project, room_ids: list[int] | None = None, all_rooms: bool = True) -> ProjectScope:
    if all_rooms or not room_ids:
        rooms = list(project.rooms)
        return ProjectScope(rooms=rooms, room_ids={room.id for room in rooms}, all_rooms_selected=True)
    selected = [room for room in project.rooms if room.id in set(room_ids)]
    return ProjectScope(rooms=selected, room_ids={room.id for room in selected}, all_rooms_selected=False)


def aggregate_geometry(scope: ProjectScope) -> GeometryTotals:
    floors = Decimal("0")
    ceilings = Decimal("0")
    walls = Decimal("0")
    perimeter = Decimal("0")
    for room in scope.rooms:
        try:
            geometry = compute_room_geometry_from_model(room)
        except GeometryValidationError:
            continue
        floors += geometry.floor_area_m2 or Decimal("0")
        ceilings += geometry.ceiling_area_m2 or Decimal("0")
        walls += geometry.wall_area_net_m2 or Decimal("0")
        perimeter += geometry.perimeter_m or Decimal("0")
    return GeometryTotals(
        floors_m2=_q(floors),
        ceilings_m2=_q(ceilings),
        walls_m2=_q(walls),
        perimeter_m=_q(perimeter),
        rooms_count=len(scope.rooms),
    )


def _category_bucket(category: str | None) -> str:
    value = (category or "").lower()
    if any(k in value for k in ("prep", "подготов", "förbe")):
        return "prep"
    if any(k in value for k in ("шпак", "spack")):
        return "filler"
    if any(k in value for k in ("paint", "покрас", "mål")):
        return "paint"
    return "other"


def calculate_labour_totals(scope: ProjectScope, operations: list[ProjectWorkItem], hourly_rate: Decimal) -> LabourTotals:
    by_category = {"prep": Decimal("0"), "filler": Decimal("0"), "paint": Decimal("0"), "other": Decimal("0")}
    total = Decimal("0")
    for item in operations:
        if not _matches_scope(item, scope):
            continue
        hours = Decimal(str(item.calculated_hours or 0))
        total += hours
        bucket = _category_bucket(item.work_type.category if item.work_type else None)
        by_category[bucket] += hours
    return LabourTotals(
        total_hours=_q(total),
        by_category={key: _q(value) for key, value in by_category.items()},
        hourly_labor_cost=_q(total * hourly_rate),
    )


def calculate_price_totals(
    *,
    scope: ProjectScope,
    operations: list[ProjectWorkItem],
    pricing_mode: str,
    hourly_rate: Decimal,
    sqm_rate: Decimal,
    fixed_price: Decimal,
) -> Decimal:
    normalized = (pricing_mode or WorkItemPricingMode.HOURLY.value).lower()
    if normalized == "fixed":
        return _q(fixed_price)
    if normalized == "sqm":
        geometry = aggregate_geometry(scope)
        return _q(geometry.walls_m2 * sqm_rate)
    scoped_sum = Decimal("0")
    for item in operations:
        if _matches_scope(item, scope):
            scoped_sum += Decimal(str(item.calculated_hours or 0))
    return _q(scoped_sum * hourly_rate)


def build_project_estimate_summary(
    *,
    project: Project,
    room_ids: list[int] | None,
    pricing_mode: str,
    hourly_rate: Decimal,
    sqm_rate: Decimal,
    fixed_price: Decimal,
) -> ProjectEstimateSummary:
    scope = build_scope(project, room_ids=room_ids, all_rooms=not room_ids)
    scoped_items = [item for item in project.work_items if _matches_scope(item, scope)]
    labour = calculate_labour_totals(scope, project.work_items, hourly_rate)
    geometry = aggregate_geometry(scope)
    total_price = calculate_price_totals(
        scope=scope,
        operations=project.work_items,
        pricing_mode=pricing_mode,
        hourly_rate=hourly_rate,
        sqm_rate=sqm_rate,
        fixed_price=fixed_price,
    )
    room_rows: list[RoomEstimateRow] = []
    has_missing_data = False
    for room in scope.rooms:
        room_items = [item for item in scoped_items if item.room_id == room.id]
        hours = _q(sum((Decimal(str(item.calculated_hours or 0)) for item in room_items), Decimal("0")))
        labour_cost = _q(
            sum(
                (Decimal(str(item.labor_cost_sek if item.labor_cost_sek is not None else (item.calculated_hours or 0) * hourly_rate)) for item in room_items),
                Decimal("0"),
            )
        )
        materials_cost = _q(sum((Decimal(str(item.materials_cost_sek or 0)) for item in room_items), Decimal("0")))
        room_missing_geometry = any(
            value is None for value in (room.floor_area_m2, room.wall_perimeter_m, room.wall_height_m)
        )
        try:
            geometry = compute_room_geometry_from_model(room)
            floor_area = _q(Decimal(str(geometry.floor_area_m2 or 0)))
            wall_area = _q(Decimal(str(geometry.wall_area_net_m2 or 0)))
            ceiling_area = _q(Decimal(str(geometry.ceiling_area_m2 or 0)))
        except GeometryValidationError:
            floor_area = None
            wall_area = None
            ceiling_area = None
            room_missing_geometry = True
        if room_missing_geometry:
            has_missing_data = True
        room_rows.append(
            RoomEstimateRow(
                room_id=room.id,
                room_name=room.name or f"#{room.id}",
                floor_area_m2=floor_area,
                wall_area_m2=wall_area,
                ceiling_area_m2=ceiling_area,
                hours=hours,
                labour_cost=labour_cost,
                materials_cost=materials_cost,
                total=_q(labour_cost + materials_cost),
                has_missing_geometry=room_missing_geometry,
            )
        )
    total_materials_cost = _q(sum((row.materials_cost for row in room_rows), Decimal("0")))
    estimate_total = _q(total_price + total_materials_cost)
    return ProjectEstimateSummary(
        scope=scope,
        geometry=geometry,
        labour=labour,
        total_price=total_price,
        materials_cost=total_materials_cost,
        estimate_total=estimate_total,
        has_missing_data=has_missing_data,
        pricing_mode=(pricing_mode or "hourly").lower(),
        room_rows=room_rows,
        scoped_work_items=scoped_items,
    )
