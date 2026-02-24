from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.material_catalog_item import MaterialCatalogItem
from app.models.material_norm import MaterialConsumptionNorm
from app.models.project import Project
from app.models.room import Room

QTY_Q = Decimal("0.0001")
MONEY_Q = Decimal("0.01")


@dataclass
class MaterialBomLineItem:
    work_type_code: str
    material_id: int | None
    material_name: str
    basis_type: str
    basis_value: Decimal
    formula: str
    theoretical_qty: Decimal
    purchase_pack_count: int | None
    purchase_qty: Decimal
    unit: str
    warnings: list[str]
    cost_total: Decimal


@dataclass
class MaterialBomReport:
    line_items: list[MaterialBomLineItem]
    materials_cost_total: Decimal
    warnings_count: int
    warnings: list[str]


@dataclass
class MaterialTotalsRow:
    material_name: str
    material_unit: str
    total_quantity: Decimal


def _q(value: Decimal, quantum: Decimal = QTY_Q) -> Decimal:
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def _active(norm: MaterialConsumptionNorm) -> bool:
    if norm.is_active is not None:
        return bool(norm.is_active)
    return bool(norm.active)


def _work_code(norm: MaterialConsumptionNorm) -> str:
    return ((norm.work_type_code or "") or (norm.applies_to_work_type or "") or (norm.work_kind or "")).strip().lower()


def _resolve_work_kind(work_item) -> str:
    code = (work_item.work_type.code or "").lower()
    category = (work_item.work_type.category or "").lower()
    name = f"{work_item.work_type.name_ru} {work_item.work_type.name_sv}".lower()
    text = f"{code} {category} {name}"
    if any(t in text for t in ("ceiling", "tak", "потол")) and any(t in text for t in ("paint", "färg", "крас")):
        return "painting_ceiling"
    if any(t in text for t in ("wall", "vägg", "стен")) and any(t in text for t in ("paint", "färg", "крас")):
        return "painting_walls"
    if any(t in text for t in ("putty", "spack", "шпат", "шпак")):
        return "putty_walls"
    if any(t in text for t in ("primer", "grunt", "грунт")):
        return "primer_walls"
    if any(t in text for t in ("floor", "golv", "пол")) and any(t in text for t in ("cover", "mask", "защит", "paper", "plastic")):
        return "floor_covering"
    return code


def _basis_value(room: Room, basis_type: str) -> Decimal:
    floor = Decimal(str(room.floor_area_m2 or 0))
    wall = Decimal(str(room.wall_area_m2 or 0))
    if wall <= 0:
        wall = Decimal(str(room.wall_perimeter_m or 0)) * Decimal(str(room.wall_height_m or 0))
    ceiling = Decimal(str(room.ceiling_area_m2 or 0))
    if ceiling <= 0:
        ceiling = floor
    if basis_type == "floor_area":
        return floor
    if basis_type == "wall_area":
        return wall
    if basis_type == "ceiling_area":
        return ceiling
    if basis_type == "walls_plus_ceilings":
        return wall + ceiling
    if basis_type == "perimeter":
        return Decimal(str(room.wall_perimeter_m or 0))
    return Decimal("0")


def _qty_per_basis(norm: MaterialConsumptionNorm) -> tuple[Decimal, Decimal]:
    consumption_qty = Decimal(str(norm.consumption_qty if norm.consumption_qty is not None else (norm.quantity_per_basis if norm.quantity_per_basis is not None else norm.consumption_value or 0)))
    per_basis_qty = Decimal(str(norm.per_basis_qty if norm.per_basis_qty is not None else 1))
    if (norm.consumption_unit or "").lower() == "per_10_m2":
        per_basis_qty = Decimal("10")
    if per_basis_qty <= 0:
        raise ValueError("per_basis_qty_must_be_gt_zero")
    if consumption_qty <= 0:
        raise ValueError("consumption_qty_must_be_gt_zero")
    return consumption_qty, per_basis_qty


def _pack_plan(required_qty: Decimal, norm: MaterialConsumptionNorm, catalog_item: MaterialCatalogItem | None) -> tuple[int | None, Decimal, Decimal, list[str]]:
    warnings: list[str] = []
    pack_size = None
    pack_unit = None
    allow_fractional = False
    price = Decimal("0")
    if catalog_item is not None:
        pack_size = Decimal(str(catalog_item.package_size or 0))
        pack_unit = (catalog_item.package_unit or catalog_item.unit or "").lower()
        price = Decimal(str(catalog_item.price_ex_vat or 0))
    elif norm.package_size is not None:
        pack_size = Decimal(str(norm.package_size or 0))
        pack_unit = (norm.package_unit or norm.material_unit or "").lower()
        price = Decimal(str(norm.default_unit_price_sek or 0))
    allow_fractional = bool(norm.allow_fractional) if norm.allow_fractional is not None else False

    if not pack_size or pack_size <= 0:
        warnings.append("MISSING_PACKAGING")
        return None, _q(required_qty), Decimal("0"), warnings

    if pack_unit and pack_unit != (norm.material_unit or "").lower():
        warnings.append("UNIT_MISMATCH")

    if allow_fractional:
        packs = required_qty / pack_size
    else:
        packs = (required_qty / pack_size).to_integral_value(rounding=ROUND_CEILING)
    purch_qty = _q(Decimal(str(packs)) * pack_size)
    total_cost = _q(Decimal(str(packs)) * price, MONEY_Q)
    return int(packs) if not allow_fractional else None, purch_qty, total_cost, warnings


def build_project_material_bom(project_id: int, db: Session, scope_mode: str = "project") -> MaterialBomReport:
    project = db.get(Project, project_id)
    if not project:
        return MaterialBomReport(line_items=[], materials_cost_total=Decimal("0.00"), warnings_count=1, warnings=["PROJECT_NOT_FOUND"])

    rooms = db.query(Room).filter(Room.project_id == project_id).all()
    rooms_by_id = {room.id: room for room in rooms}
    norms = [n for n in db.query(MaterialConsumptionNorm).all() if _active(n)]
    norms_by_work_code = {_work_code(n): n for n in norms if _work_code(n)}

    line_items: list[MaterialBomLineItem] = []
    global_warnings: list[str] = []
    total_cost = Decimal("0")

    for work_item in project.work_items:
        work_code = ((work_item.work_type.code if work_item.work_type else "") or "").strip().lower()
        work_kind = _resolve_work_kind(work_item)
        norm = norms_by_work_code.get(work_code) or norms_by_work_code.get(work_kind)
        if norm is None:
            global_warnings.append(f"No material norm configured for work_type={work_code}")
            continue

        basis_type = (norm.basis_type or "custom").lower()
        if scope_mode == "room" and work_item.room_id:
            scoped_rooms = [rooms_by_id[work_item.room_id]] if work_item.room_id in rooms_by_id else []
        elif work_item.scope_mode == "room" and work_item.room_id:
            scoped_rooms = [rooms_by_id[work_item.room_id]] if work_item.room_id in rooms_by_id else []
        else:
            scoped_rooms = rooms
        basis_value = Decimal(str(len(scoped_rooms))) if basis_type == "room_count" else sum((_basis_value(room, basis_type) for room in scoped_rooms), start=Decimal("0"))
        if basis_type == "custom":
            basis_value = Decimal(str(work_item.quantity or 0))
        if basis_value <= 0:
            global_warnings.append(f"Missing geometry for basis_type={basis_type} work_type={work_code}")
            continue

        consumption_qty, per_basis_qty = _qty_per_basis(norm)
        theoretical_qty = (basis_value * consumption_qty) / per_basis_qty

        coats = Decimal("1")
        if bool(norm.layers_multiplier_enabled) and Decimal(str(work_item.quantity or 0)) > 0:
            coats = Decimal(str(work_item.quantity or 1))
        theoretical_qty = theoretical_qty * coats

        waste = Decimal(str(norm.waste_percent if norm.waste_percent is not None else (norm.waste_factor_pct or 0)))
        theoretical_qty = theoretical_qty * (Decimal("1") + waste / Decimal("100"))
        theoretical_qty = _q(theoretical_qty)

        catalog_item = db.get(MaterialCatalogItem, norm.material_catalog_item_id) if norm.material_catalog_item_id else None
        pack_count, purchase_qty, cost_total, line_warnings = _pack_plan(theoretical_qty, norm, catalog_item)
        total_cost += cost_total
        unit = (norm.material_unit or norm.consumption_unit or "pcs").lower()
        formula = f"{_q(basis_value)} {(norm.per_basis_unit or norm.basis_unit or 'm2')} × ({consumption_qty} {unit} / {per_basis_qty} {(norm.per_basis_unit or norm.basis_unit or 'm2')}) × {coats} coats"
        line_items.append(
            MaterialBomLineItem(
                work_type_code=work_code,
                material_id=norm.material_catalog_item_id,
                material_name=(catalog_item.name if catalog_item else (norm.material_name or norm.name or "Material")),
                basis_type=basis_type,
                basis_value=_q(basis_value),
                formula=formula,
                theoretical_qty=theoretical_qty,
                purchase_pack_count=pack_count,
                purchase_qty=purchase_qty,
                unit=unit,
                warnings=line_warnings,
                cost_total=cost_total,
            )
        )

    for item in line_items:
        global_warnings.extend(item.warnings)

    return MaterialBomReport(
        line_items=line_items,
        materials_cost_total=_q(total_cost, MONEY_Q),
        warnings_count=len(global_warnings),
        warnings=global_warnings,
    )


def aggregate_totals(report: MaterialBomReport) -> list[MaterialTotalsRow]:
    grouped: dict[tuple[str, str], Decimal] = {}
    for row in report.line_items:
        key = (row.material_name, row.unit)
        grouped[key] = grouped.get(key, Decimal("0")) + row.theoretical_qty
    return [MaterialTotalsRow(material_name=k[0], material_unit=k[1], total_quantity=_q(v)) for k, v in sorted(grouped.items())]
