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
from app.services.geometry import compute_room_geometry_from_model, geometry_completeness

ScopeApplyMode = Literal["single_room", "selected_rooms", "all_rooms", "project_aggregate", "custom_qty"]
DuplicateMode = Literal["append", "skip_same_work_in_room"]


class ScopeApplySummary(BaseModel):
    created_count: int
    skipped_count: int
    warnings: list[str]
    created_item_ids: list[int]


class ScopePreviewSummary(BaseModel):
    target_rooms_count: int
    estimated_quantity: Decimal
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
    if scope_apply_mode == "project_aggregate":
        return list(project.rooms)
    return []


def _resolve_preview_basis(work_type: WorkType, basis_type: str | None) -> str:
    if basis_type:
        basis = basis_type.strip().lower()
        if basis == "wall_area":
            return "wall_area_m2"
        return basis

    category = (work_type.category or "").lower()
    if _is_wall_and_ceiling_work(work_type):
        return "wall_and_ceiling"
    if any(marker in category for marker in ("ceiling", "потол", "tak")):
        return "ceiling_area_m2"
    if any(marker in category for marker in ("wall", "стен", "vägg")):
        return "wall_area_m2"
    if any(marker in category for marker in ("floor", "пол", "golv")):
        return "floor_area_m2"
    return "floor_area_m2"


def build_scope_preview(
    *,
    project: Project,
    work_type: WorkType,
    scope_apply_mode: ScopeApplyMode,
    room_ids: list[int] | None = None,
    room_id: int | None = None,
    layers: Decimal = Decimal("1.00"),
    difficulty_factor: Decimal = Decimal("1.00"),
    basis_type: str | None = None,
    manual_qty: Decimal | None = None,
) -> ScopePreviewSummary:
    warnings: list[str] = []
    normalized_scope = (scope_apply_mode or "single_room").strip().lower()
    if normalized_scope in {"room", "selected_room"}:
        normalized_scope = "single_room"
    if normalized_scope == "project":
        normalized_scope = "project_aggregate"
    if normalized_scope not in {"single_room", "selected_rooms", "all_rooms", "project_aggregate", "custom_qty"}:
        normalized_scope = "single_room"

    if normalized_scope == "custom_qty":
        custom_quantity = _to_decimal(manual_qty)
        est_hours = (custom_quantity * Decimal(str(work_type.hours_per_unit or 0)) * difficulty_factor).quantize(Decimal("0.01"))
        return ScopePreviewSummary(
            target_rooms_count=0,
            estimated_quantity=custom_quantity,
            total_floor_area=Decimal("0.00"),
            total_wall_area=Decimal("0.00"),
            total_ceiling_area=Decimal("0.00"),
            estimated_labour_hours=est_hours,
            warnings=[],
        )

    preview_basis = _resolve_preview_basis(work_type, basis_type)
    target_rooms = _resolve_target_rooms(project, normalized_scope, room_ids, room_id)
    total_floor = Decimal("0")
    total_wall = Decimal("0")
    total_ceiling = Decimal("0")
    total_quantity = Decimal("0")

    for room in target_rooms:
        geom = compute_room_geometry_from_model(room)
        total_floor += Decimal(str(geom.floor_area_m2 or 0))
        wall_area = geom.wall_area_m2 if geom.wall_area_m2 is not None else geom.wall_area_net_m2
        total_wall += Decimal(str(wall_area or 0))
        total_ceiling += Decimal(str(geom.ceiling_area_m2 or 0))

        completeness = geometry_completeness(geom)
        room_warning = f"INCOMPLETE_GEOMETRY:{room.id}"
        qty: Decimal | None
        if preview_basis == "wall_area_m2":
            qty = Decimal(str(wall_area or 0)) * layers
            if not completeness["walls"]:
                warnings.append(room_warning)
                continue
        elif preview_basis == "ceiling_area_m2":
            qty = Decimal(str(geom.ceiling_area_m2 or geom.floor_area_m2 or 0)) * layers
            if not completeness["ceiling"]:
                warnings.append(room_warning)
                continue
        elif preview_basis == "wall_and_ceiling":
            qty = (Decimal(str(wall_area or 0)) + Decimal(str(geom.ceiling_area_m2 or geom.floor_area_m2 or 0))) * layers
            if not (completeness["walls"] and completeness["ceiling"]):
                warnings.append(room_warning)
                continue
        else:
            qty = _resolve_bulk_quantity_for_room(room, work_type, layers=layers)
            if preview_basis == "floor_area_m2" and not completeness["floor"]:
                warnings.append(room_warning)
                continue

        if qty is None or qty <= 0:
            warnings.append(f"missing_quantity:{room.name}")
            continue
        total_quantity += qty

    if normalized_scope == "project_aggregate" and preview_basis not in {"wall_area_m2", "ceiling_area_m2", "wall_and_ceiling", "floor_area_m2"}:
        quantity = resolve_project_quantity(target_rooms or list(project.rooms), work_type, layers=layers)
        total_quantity = Decimal(str(quantity or 0))

    hours_per_unit = Decimal(str(work_type.hours_per_unit or 0))
    est_hours = (total_quantity * hours_per_unit * difficulty_factor).quantize(Decimal("0.01"))
    return ScopePreviewSummary(
        target_rooms_count=len(target_rooms),
        estimated_quantity=_to_decimal(total_quantity),
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
    group_rooms = selected_ids if scope_apply_mode == "selected_rooms" else []
    source_group_ref = payload.get("source_group_ref") or f"bulk:{scope_apply_mode}:wt{work_type.id}:rooms={','.join(str(v) for v in group_rooms) or 'all'}:layers={Decimal(str(payload.get('layers') or '1')).quantize(Decimal('0.01'))}"

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
        db.query(ProjectWorkItem).filter(
            ProjectWorkItem.project_id == project.id,
            ProjectWorkItem.source_group_ref == source_group_ref,
        ).delete(synchronize_session=False)
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
            source_group_ref=source_group_ref,
            comment=comment,
        )
        db.add(item)
        db.flush()
        created_ids.append(item.id)
        return ScopeApplySummary(created_count=1, skipped_count=0, warnings=[], created_item_ids=created_ids)

    target_rooms = _resolve_target_rooms(project, scope_apply_mode, selected_ids, room_id)
    if scope_apply_mode in {"all_rooms", "selected_rooms"}:
        db.query(ProjectWorkItem).filter(
            ProjectWorkItem.project_id == project.id,
            ProjectWorkItem.source_group_ref == source_group_ref,
        ).delete(synchronize_session=False)

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
            source_group_ref=source_group_ref,
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
