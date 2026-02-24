from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.material_norm import MaterialConsumptionNorm
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room

QTY_Q = Decimal("0.0001")

VALID_BASIS_TYPES = {"floor_area", "ceiling_area", "wall_area", "opening_area", "perimeter", "manual_quantity"}


@dataclass
class MaterialNeedRow:
    material_name: str
    source_work_item_id: int
    rule_id: int
    basis_type: str
    basis_quantity: Decimal
    norm_value: Decimal
    waste_factor_pct: Decimal
    calculated_quantity: Decimal
    material_unit: str


@dataclass
class MaterialNeedTotal:
    material_name: str
    material_unit: str
    total_quantity: Decimal


def _q(value: Decimal) -> Decimal:
    return value.quantize(QTY_Q, rounding=ROUND_HALF_UP)


def resolve_work_kind(work_item: ProjectWorkItem) -> str:
    code = (work_item.work_type.code or "").lower()
    category = (work_item.work_type.category or "").lower()
    name = f"{work_item.work_type.name_ru} {work_item.work_type.name_sv}".lower()
    text = f"{code} {category} {name}"
    if any(token in text for token in ("ceiling", "tak", "потол")) and any(token in text for token in ("paint", "färg", "крас")):
        return "painting_ceiling"
    if any(token in text for token in ("wall", "vägg", "стен")) and any(token in text for token in ("paint", "färg", "крас")):
        return "painting_walls"
    if any(token in text for token in ("putty", "spack", "шпат", "шпак")):
        return "putty_walls"
    if any(token in text for token in ("primer", "grunt", "грунт")):
        return "primer_walls"
    if any(token in text for token in ("floor", "golv", "пол")) and any(token in text for token in ("cover", "mask", "защит", "paper", "plastic")):
        return "floor_covering"
    return code


def _room_basis_quantity(room: Room, basis_type: str) -> Decimal:
    floor = Decimal(str(room.floor_area_m2 or 0))
    ceiling = Decimal(str(room.ceiling_area_m2 or 0))
    if ceiling <= 0:
        ceiling = floor
    wall = Decimal(str(room.wall_area_m2 or 0))
    if wall <= 0:
        wall = Decimal(str(room.wall_perimeter_m or 0)) * Decimal(str(room.wall_height_m or 0))
    openings = Decimal(str(room.openings_area_m2 or 0))
    perimeter = Decimal(str(room.wall_perimeter_m or 0))
    mapping = {
        "floor_area": floor,
        "ceiling_area": ceiling,
        "wall_area": wall,
        "opening_area": openings,
        "perimeter": perimeter,
    }
    return mapping.get(basis_type, Decimal("0"))


def _scope_rooms_for_work_item(work_item: ProjectWorkItem, rooms_by_project: dict[int, list[Room]]) -> list[Room]:
    all_rooms = rooms_by_project.get(work_item.project_id, [])
    if work_item.room_id:
        return [room for room in all_rooms if room.id == work_item.room_id]
    return all_rooms


def _rule_basis_type(rule: MaterialConsumptionNorm) -> str:
    if rule.basis_type:
        return rule.basis_type
    return {
        "wall": "wall_area",
        "ceiling": "ceiling_area",
        "floor": "floor_area",
    }.get((rule.surface_type or "").lower(), "manual_quantity")


def _rule_norm_value(rule: MaterialConsumptionNorm) -> Decimal:
    if rule.quantity_per_basis is not None:
        return Decimal(str(rule.quantity_per_basis or 0))
    value = Decimal(str(rule.consumption_value or 0))
    if (rule.consumption_unit or "").lower() == "per_10_m2":
        return value / Decimal("10")
    return value


def _rule_work_kind(rule: MaterialConsumptionNorm) -> str:
    return (rule.work_kind or rule.applies_to_work_type or "").strip().lower()


def _rule_active(rule: MaterialConsumptionNorm) -> bool:
    if rule.is_active is not None:
        return bool(rule.is_active)
    return bool(rule.active)


def calculate_material_needs_for_work_item(db: Session, project: Project, work_item: ProjectWorkItem) -> list[MaterialNeedRow]:
    work_kind = resolve_work_kind(work_item)
    rules = [
        rule
        for rule in db.query(MaterialConsumptionNorm).all()
        if _rule_active(rule) and _rule_work_kind(rule) == work_kind
    ]
    if not rules:
        return []

    rooms = db.query(Room).filter(Room.project_id == project.id).all()
    scoped_rooms = _scope_rooms_for_work_item(work_item, {project.id: rooms})
    needs: list[MaterialNeedRow] = []
    for rule in rules:
        basis_type = _rule_basis_type(rule)
        if basis_type not in VALID_BASIS_TYPES:
            continue
        if basis_type == "manual_quantity":
            basis_qty = Decimal(str(work_item.quantity or 0))
        else:
            basis_qty = sum((_room_basis_quantity(room, basis_type) for room in scoped_rooms), start=Decimal("0"))
        norm = _rule_norm_value(rule)
        waste = Decimal(str(rule.waste_factor_pct if rule.waste_factor_pct is not None else (rule.waste_percent or 0)))
        quantity = basis_qty * norm * (Decimal("1") + waste / Decimal("100"))
        needs.append(
            MaterialNeedRow(
                material_name=rule.material_name,
                source_work_item_id=work_item.id,
                rule_id=rule.id,
                basis_type=basis_type,
                basis_quantity=_q(basis_qty),
                norm_value=_q(norm),
                waste_factor_pct=_q(waste),
                calculated_quantity=_q(quantity),
                material_unit=rule.material_unit,
            )
        )
    return needs


def calculate_material_needs_for_project(db: Session, project_id: int) -> tuple[list[MaterialNeedRow], list[MaterialNeedTotal]]:
    project = db.get(Project, project_id)
    if not project:
        return [], []
    rows: list[MaterialNeedRow] = []
    for item in project.work_items:
        rows.extend(calculate_material_needs_for_work_item(db, project, item))

    grouped: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    for row in rows:
        grouped[(row.material_name, row.material_unit)] += row.calculated_quantity

    totals = [
        MaterialNeedTotal(material_name=name, material_unit=unit, total_quantity=_q(total))
        for (name, unit), total in sorted(grouped.items())
    ]
    return rows, totals
