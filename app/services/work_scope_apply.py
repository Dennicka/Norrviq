from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.estimates import (
    SCOPE_MODE_PROJECT,
    SCOPE_MODE_ROOM,
    WorkItemPricingMode,
    _norm_mode,
    _resolve_bulk_quantity_for_room,
    resolve_project_quantity,
)
from app.services.geometry import compute_room_geometry_from_model

ScopeApplyMode = Literal["single_room", "selected_rooms", "all_rooms", "project_aggregate"]
DuplicateMode = Literal["append", "skip_same_work_in_room"]


class ScopeApplySummary(BaseModel):
    created_count: int
    skipped_count: int
    warnings: list[str]
    created_item_ids: list[int]


class ScopePreviewSummary(BaseModel):
    target_rooms_count: int
    total_floor_area: Decimal
    total_wall_area: Decimal
    total_ceiling_area: Decimal
    estimated_labour_hours: Decimal
    warnings: list[str]


def _to_decimal(value: Decimal | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _is_wall_and_ceiling_work(work_type: WorkType) -> bool:
    text = " ".join(
        [
            str(work_type.code or ""),
            str(work_type.category or ""),
            str(work_type.name_ru or ""),
            str(work_type.name_sv or ""),
        ]
    ).lower()
    return (
        "wall" in text or "стен" in text or "vägg" in text
    ) and ("ceiling" in text or "потол" in text or "tak" in text)


def _estimate_area_for_room(room: Room, work_type: WorkType) -> Decimal:
    geom = compute_room_geometry_from_model(room)
    category = (work_type.category or "").lower()
    if _is_wall_and_ceiling_work(work_type):
        return _to_decimal((geom.wall_area_net_m2 or Decimal("0")) + (geom.ceiling_area_m2 or Decimal("0")))
    if any(marker in category for marker in ("ceiling", "потол", "tak")):
        return _to_decimal(geom.ceiling_area_m2)
    if any(marker in category for marker in ("wall", "стен", "vägg")):
        return _to_decimal(geom.wall_area_net_m2)
    if any(marker in category for marker in ("floor", "пол", "golv")):
        return _to_decimal(geom.floor_area_m2)
    return _to_decimal(geom.floor_area_m2)


def _resolve_target_rooms(project: Project, scope_apply_mode: ScopeApplyMode, room_ids: list[int] | None, room_id: int | None) -> list[Room]:
    rooms_by_id = {room.id: room for room in project.rooms}
    if scope_apply_mode == "single_room":
        if room_id is None:
            return []
        room = rooms_by_id.get(room_id)
        return [room] if room else []
    if scope_apply_mode == "selected_rooms":
        room_ids = room_ids or []
        return [rooms_by_id[rid] for rid in room_ids if rid in rooms_by_id]
    if scope_apply_mode == "all_rooms":
        return list(project.rooms)
    return []


def build_scope_preview(*, project: Project, work_type: WorkType, scope_apply_mode: ScopeApplyMode, room_ids: list[int] | None = None, room_id: int | None = None, layers: Decimal = Decimal("1.00"), difficulty_factor: Decimal = Decimal("1.00")) -> ScopePreviewSummary:
    warnings: list[str] = []
    target_rooms = _resolve_target_rooms(project, scope_apply_mode, room_ids, room_id)
    total_floor = Decimal("0")
    total_wall = Decimal("0")
    total_ceiling = Decimal("0")
    total_quantity = Decimal("0")

    for room in target_rooms:
        geom = compute_room_geometry_from_model(room)
        if not geom.is_complete:
            warnings.append(f"missing_geometry:{room.name}")
            continue
        total_floor += Decimal(str(geom.floor_area_m2 or 0))
        total_wall += Decimal(str(geom.wall_area_net_m2 or 0))
        total_ceiling += Decimal(str(geom.ceiling_area_m2 or 0))
        qty = _resolve_bulk_quantity_for_room(room, work_type, layers=layers)
        if qty is None or qty <= 0:
            warnings.append(f"missing_quantity:{room.name}")
            continue
        total_quantity += qty

    if scope_apply_mode == "project_aggregate":
        quantity = resolve_project_quantity(target_rooms or list(project.rooms), work_type, layers=layers)
        total_quantity = Decimal(str(quantity or 0))
        total_floor = sum((Decimal(str(compute_room_geometry_from_model(r).floor_area_m2 or 0)) for r in project.rooms), Decimal("0"))
        total_wall = sum((Decimal(str(compute_room_geometry_from_model(r).wall_area_net_m2 or 0)) for r in project.rooms), Decimal("0"))
        total_ceiling = sum((Decimal(str(compute_room_geometry_from_model(r).ceiling_area_m2 or 0)) for r in project.rooms), Decimal("0"))

    hours_per_unit = Decimal(str(work_type.hours_per_unit or 0))
    est_hours = (total_quantity * hours_per_unit * difficulty_factor).quantize(Decimal("0.01"))
    return ScopePreviewSummary(
        target_rooms_count=len(target_rooms) if scope_apply_mode != "project_aggregate" else len(project.rooms),
        total_floor_area=_to_decimal(total_floor),
        total_wall_area=_to_decimal(total_wall),
        total_ceiling_area=_to_decimal(total_ceiling),
        estimated_labour_hours=est_hours,
        warnings=warnings,
    )


def apply_work_item_to_scope(project_id: int, payload: dict, db: Session) -> ScopeApplySummary:
    project = db.get(Project, project_id)
    if not project:
        return ScopeApplySummary(created_count=0, skipped_count=0, warnings=["project_not_found"], created_item_ids=[])

    work_type = db.get(WorkType, int(payload.get("work_type_id") or 0))
    if not work_type:
        return ScopeApplySummary(created_count=0, skipped_count=0, warnings=["work_type_required"], created_item_ids=[])

    scope_apply_mode = (payload.get("scope_apply_mode") or payload.get("scope_mode") or "single_room").strip().lower()
    if scope_apply_mode in {"room", "selected_room"}:
        scope_apply_mode = "single_room"
    if scope_apply_mode == "project":
        scope_apply_mode = "project_aggregate"
    if scope_apply_mode not in {"single_room", "selected_rooms", "all_rooms", "project_aggregate"}:
        scope_apply_mode = "single_room"

    duplicate_mode = (payload.get("duplicate_mode") or "append").strip().lower()
    if duplicate_mode not in {"append", "skip_same_work_in_room"}:
        duplicate_mode = "append"

    room_id = int(payload.get("room_id")) if str(payload.get("room_id") or "").isdigit() else None
    raw_selected = payload.get("selected_room_ids") or payload.get("room_ids") or []
    if isinstance(raw_selected, str):
        raw_selected = [raw_selected]
    selected_ids = sorted({int(raw) for raw in raw_selected if str(raw).isdigit()})

    layers = Decimal(str(payload.get("layers") or "1"))
    difficulty_factor = Decimal(str(payload.get("difficulty_factor") or "1"))
    comment = payload.get("comment")

    pricing_mode = _norm_mode(str(payload.get("pricing_mode") or WorkItemPricingMode.HOURLY.value)).value
    hourly_rate_sek = Decimal(str(payload["hourly_rate_sek"])) if payload.get("hourly_rate_sek") not in (None, "") else None
    area_rate_sek = Decimal(str(payload["area_rate_sek"])) if payload.get("area_rate_sek") not in (None, "") else None
    fixed_price_sek = Decimal(str(payload["fixed_price_sek"])) if payload.get("fixed_price_sek") not in (None, "") else None

    warnings: list[str] = []
    created_ids: list[int] = []

    if scope_apply_mode == "project_aggregate":
        quantity = resolve_project_quantity(list(project.rooms), work_type, layers=layers)
        if quantity is None or quantity <= 0:
            return ScopeApplySummary(created_count=0, skipped_count=1, warnings=["missing_project_geometry"], created_item_ids=[])

        item = ProjectWorkItem(
            project_id=project.id,
            work_type_id=work_type.id,
            scope_mode=SCOPE_MODE_PROJECT,
            room_id=None,
            quantity=quantity.quantize(Decimal("0.01")),
            difficulty_factor=difficulty_factor,
            pricing_mode=pricing_mode,
            hourly_rate_sek=hourly_rate_sek,
            area_rate_sek=area_rate_sek,
            fixed_price_sek=fixed_price_sek,
            comment=comment,
        )
        db.add(item)
        db.flush()
        created_ids.append(item.id)
        return ScopeApplySummary(created_count=1, skipped_count=0, warnings=[], created_item_ids=created_ids)

    target_rooms = _resolve_target_rooms(project, scope_apply_mode, selected_ids, room_id)

    for room in target_rooms:
        if duplicate_mode == "skip_same_work_in_room":
            existing = (
                db.query(ProjectWorkItem)
                .filter(
                    ProjectWorkItem.project_id == project.id,
                    ProjectWorkItem.room_id == room.id,
                    ProjectWorkItem.scope_mode == SCOPE_MODE_ROOM,
                    ProjectWorkItem.work_type_id == work_type.id,
                )
                .first()
            )
            if existing:
                warnings.append(f"duplicate_skipped:{room.name}")
                continue

        quantity = _resolve_bulk_quantity_for_room(room, work_type, layers=layers)
        if quantity is None or quantity <= 0:
            warnings.append(f"missing_geometry:{room.name}")
            continue

        item = ProjectWorkItem(
            project_id=project.id,
            work_type_id=work_type.id,
            scope_mode=SCOPE_MODE_ROOM,
            room_id=room.id,
            quantity=quantity.quantize(Decimal("0.01")),
            difficulty_factor=difficulty_factor,
            pricing_mode=pricing_mode,
            hourly_rate_sek=hourly_rate_sek,
            area_rate_sek=area_rate_sek,
            fixed_price_sek=fixed_price_sek,
            comment=comment,
        )
        db.add(item)
        db.flush()
        created_ids.append(item.id)

    return ScopeApplySummary(
        created_count=len(created_ids),
        skipped_count=max(len(target_rooms) - len(created_ids), 0),
        warnings=warnings,
        created_item_ids=created_ids,
    )
