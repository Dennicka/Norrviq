from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

from sqlalchemy.orm import Session, joinedload

from app.models.cost import CostCategory, ProjectCostItem
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.material import Material
from app.models.material_catalog_item import MaterialCatalogItem
from app.models.material_norm import MaterialConsumptionNorm
from app.models.material_consumption_override import MaterialConsumptionOverride
from app.models.material_recipe import MaterialRecipe
from app.models.paint_system import PaintSystemSurface, ProjectPaintSettings, RoomPaintSettings
from app.models.project import Project, ProjectWorkItem
from app.models.project_material_settings import ProjectMaterialSettings
from app.models.room import Room
from app.models.supplier_material_price import SupplierMaterialPrice
from app.services.takeoff import compute_project_areas, get_or_create_project_takeoff_settings
from app.services.request_cache import RequestCache, cache_key
from app.services.procurement_rounding import ProcurementRoundingPolicy, compute_packs_needed, normalize_policy
from app.services.unit_conversion import UnitConversionError, convert_qty, normalize_unit

UNIT_Q = Decimal("0.0001")
MONEY_Q = Decimal("0.01")


@dataclass
class BOMDetail:
    source: str
    room_id: int | None
    room_name: str | None
    area_m2_used: Decimal
    system_id: int | None
    system_name: str | None
    step_id: int | None
    step_order: int | None
    recipe_id: int


@dataclass
class BOMItem:
    material_id: int
    name: str
    unit: str
    area_m2_used: Decimal
    qty_required_unit: Decimal
    packs_count: int | None
    pack_size: Decimal | None
    qty_final_unit: Decimal
    cost_ex_vat: Decimal
    sell_ex_vat: Decimal
    details: list[BOMDetail]
    source_works: str = ""
    surface_type: str = ""
    coats: Decimal = Decimal("1")
    norm_label: str = ""
    waste_percent: Decimal = Decimal("0")


@dataclass
class BOMReport:
    basis_used: str
    total_floor_m2: Decimal
    total_wall_m2: Decimal
    total_ceiling_m2: Decimal
    total_paintable_m2: Decimal
    items: list[BOMItem]
    total_cost_ex_vat: Decimal
    total_sell_ex_vat: Decimal
    warnings: list[str]


class ProcurementStrategy(str, Enum):
    CHEAPEST = "CHEAPEST"
    PREFERRED_FIRST = "PREFERRED_FIRST"
    FIXED_SUPPLIER = "FIXED_SUPPLIER"


@dataclass
class ProcurementLine:
    material_id: int
    material_name: str
    qty: Decimal
    unit: str
    supplier_id: int | None
    supplier_name: str | None
    price_unit: str | None
    unit_price_ex_vat: Decimal | None
    packs_needed: Decimal | None
    purchase_qty: Decimal
    line_total_cost_ex_vat: Decimal
    warnings: list[str]


@dataclass
class ProcurementPlan:
    strategy: ProcurementStrategy
    lines: list[ProcurementLine]
    total_cost_ex_vat: Decimal
    warnings: list[str]


def _q(v: Decimal, q: Decimal = UNIT_Q) -> Decimal:
    return v.quantize(q, rounding=ROUND_HALF_UP)


def _qm(v: Decimal) -> Decimal:
    return _q(v, MONEY_Q)


def get_or_create_project_material_settings(db: Session, project_id: int) -> ProjectMaterialSettings:
    settings = db.query(ProjectMaterialSettings).filter(ProjectMaterialSettings.project_id == project_id).first()
    if settings:
        return settings
    settings = ProjectMaterialSettings(project_id=project_id)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings




def get_or_create_project_paint_settings(db: Session, project_id: int) -> ProjectPaintSettings:
    settings = db.query(ProjectPaintSettings).filter(ProjectPaintSettings.project_id == project_id).first()
    if settings:
        return settings
    settings = ProjectPaintSettings(project_id=project_id)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def get_or_create_room_paint_settings(db: Session, room_id: int) -> RoomPaintSettings:
    settings = db.query(RoomPaintSettings).filter(RoomPaintSettings.room_id == room_id).first()
    if settings:
        return settings
    settings = RoomPaintSettings(room_id=room_id)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


@dataclass
class ResolvedMaterialNorm:
    quantity_per_unit: Decimal
    base_unit_size: Decimal
    unit_basis: str
    surface_kind: str
    waste_percent: Decimal
    source: str


def _normalize_surface_kind(surface: str | None) -> str:
    raw = (surface or "").strip().lower()
    if raw in {"wall", "walls"}:
        return "walls"
    if raw in {"ceiling", "ceilings"}:
        return "ceiling"
    if raw in {"floor", "floors"}:
        return "floor"
    if raw in {"combined", "paintable", "custom"}:
        return "combined"
    if raw in {"piece", "pieces"}:
        return "pieces"
    return "combined"


def _rule_from_norm(norm: MaterialConsumptionNorm) -> ResolvedMaterialNorm:
    consumption_value = Decimal(str(norm.consumption_value or 0))
    if (norm.consumption_unit or "").lower() == "per_10_m2":
        base_unit_size = Decimal("10")
    else:
        base_unit_size = Decimal("1")
    return ResolvedMaterialNorm(
        quantity_per_unit=consumption_value,
        base_unit_size=base_unit_size,
        unit_basis="m2",
        surface_kind=_normalize_surface_kind(norm.surface_type),
        waste_percent=Decimal(str(norm.waste_percent if norm.waste_percent is not None else 10)),
        source="default",
    )


def resolve_material_norm(db: Session, project_id: int, room_id: int | None, work_type_id: int, material_id: int | None, surface_kind: str, default_norm: MaterialConsumptionNorm) -> ResolvedMaterialNorm:
    if material_id is not None:
        normalized_surface = _normalize_surface_kind(surface_kind)
        room_override = db.query(MaterialConsumptionOverride).filter(
            MaterialConsumptionOverride.project_id == project_id,
            MaterialConsumptionOverride.room_id == room_id,
            MaterialConsumptionOverride.work_type_id == work_type_id,
            MaterialConsumptionOverride.material_id == material_id,
            MaterialConsumptionOverride.surface_kind == normalized_surface,
            MaterialConsumptionOverride.is_active.is_(True),
        ).first()
        if room_override:
            return ResolvedMaterialNorm(
                quantity_per_unit=Decimal(str(room_override.quantity_per_unit)),
                base_unit_size=Decimal(str(room_override.base_unit_size or 1)),
                unit_basis=(room_override.unit_basis or "m2").lower(),
                surface_kind=normalized_surface,
                waste_percent=Decimal(str(room_override.waste_factor_percent if room_override.waste_factor_percent is not None else (default_norm.waste_percent if default_norm.waste_percent is not None else 10))),
                source="room_override",
            )
        project_override = db.query(MaterialConsumptionOverride).filter(
            MaterialConsumptionOverride.project_id == project_id,
            MaterialConsumptionOverride.room_id.is_(None),
            MaterialConsumptionOverride.work_type_id == work_type_id,
            MaterialConsumptionOverride.material_id == material_id,
            MaterialConsumptionOverride.surface_kind == normalized_surface,
            MaterialConsumptionOverride.is_active.is_(True),
        ).first()
        if project_override:
            return ResolvedMaterialNorm(
                quantity_per_unit=Decimal(str(project_override.quantity_per_unit)),
                base_unit_size=Decimal(str(project_override.base_unit_size or 1)),
                unit_basis=(project_override.unit_basis or "m2").lower(),
                surface_kind=normalized_surface,
                waste_percent=Decimal(str(project_override.waste_factor_percent if project_override.waste_factor_percent is not None else (default_norm.waste_percent if default_norm.waste_percent is not None else 10))),
                source="project_override",
            )
    return _rule_from_norm(default_norm)


def _resolve_area_for_surface(room: Room, surface_kind: str) -> tuple[Decimal, bool]:
    floor = Decimal(str(room.floor_area_m2 or 0))
    wall = Decimal(str(room.wall_area_m2 or 0))
    if wall <= 0 and room.wall_perimeter_m is not None and room.wall_height_m is not None:
        wall = Decimal(str(room.wall_perimeter_m or 0)) * Decimal(str(room.wall_height_m or 0))
    ceiling = Decimal(str(room.ceiling_area_m2 or 0))
    if surface_kind == "walls":
        return wall, wall > 0
    if surface_kind == "ceiling":
        return ceiling, ceiling > 0
    if surface_kind == "floor":
        return floor, floor > 0
    if surface_kind == "combined":
        total = wall + ceiling
        return total, total > 0
    return Decimal("0"), False
def _resolve_surface_area(room: Room, surface_type: str) -> Decimal:
    floor = Decimal(str(room.floor_area_m2 or 0))
    wall = Decimal(str(room.wall_area_m2 or 0))
    if wall <= 0:
        wall = Decimal(str(room.wall_perimeter_m or 0)) * Decimal(str(room.wall_height_m or 0))
    ceiling = Decimal(str(room.ceiling_area_m2 or 0))
    if ceiling <= 0:
        ceiling = floor
    if surface_type == "ceiling":
        return ceiling
    if surface_type == "wall":
        return wall
    if surface_type == "floor":
        return floor
    return floor


def _infer_surface_for_work(work_item: ProjectWorkItem) -> str:
    category = (work_item.work_type.category or "").lower()
    code = (work_item.work_type.code or "").lower()
    text = f"{category} {code}"
    if any(k in text for k in ("ceiling", "tak", "потол")):
        return "ceiling"
    if any(k in text for k in ("wall", "vägg", "стен")):
        return "wall"
    if any(k in text for k in ("floor", "golv", "пол", "protect", "защит", "skydd")):
        return "floor"
    return "custom"


def _compute_bom_from_norms(db: Session, project: Project, warnings: list[str]) -> list[BOMItem]:
    norms = db.query(MaterialConsumptionNorm).filter(MaterialConsumptionNorm.active.is_(True)).all()
    if not norms:
        return []
    norms_by_work: dict[str, list[MaterialConsumptionNorm]] = {}
    for norm in norms:
        norms_by_work.setdefault((norm.applies_to_work_type or "").strip().lower(), []).append(norm)
    rooms = {r.id: r for r in db.query(Room).filter(Room.project_id == project.id).all()}
    if not rooms:
        return []
    materials = {m.id: m for m in db.query(Material).filter(Material.is_active.is_(True)).all()}
    materials_by_name_sv = {m.name_sv.lower(): m for m in materials.values()}
    materials_by_code = {m.code.lower(): m for m in materials.values() if m.code}
    norm_catalog_ids = {norm.material_catalog_item_id for norm in norms if norm.material_catalog_item_id is not None}
    catalog_by_id: dict[int, MaterialCatalogItem] = {}
    if norm_catalog_ids:
        catalog_by_id = {
            item.id: item
            for item in db.query(MaterialCatalogItem)
            .filter(MaterialCatalogItem.id.in_(norm_catalog_ids), MaterialCatalogItem.is_active.is_(True))
            .all()
        }

    grouped: dict[str, dict] = {}
    for item in sorted(project.work_items, key=lambda wi: wi.id or 0):
        work_code = (item.work_type.code or "").strip().lower()
        matched_norms = norms_by_work.get(work_code, [])
        if not matched_norms:
            warnings.append(f"work:{work_code}:MISSING_NORM")
            continue

        target_rooms = [rooms[item.room_id]] if item.room_id in rooms else list(rooms.values())
        for norm in matched_norms:
            default_surface = _normalize_surface_kind(norm.surface_type or _infer_surface_for_work(item))
            material = None
            catalog = None
            display_name = (norm.material_name or "").strip()
            if norm.material_catalog_item_id is not None:
                catalog = catalog_by_id.get(norm.material_catalog_item_id)
                if catalog is not None:
                    material = materials_by_code.get((catalog.material_code or "").strip().lower())
                    if material is not None:
                        display_name = (catalog.name or material.name_sv or display_name).strip()
                    else:
                        warnings.append(f"norm:{norm.id}:MISSING_MATERIAL_FOR_CATALOG_CODE:{catalog.material_code}")

            if material is None:
                material = materials_by_name_sv.get((norm.material_name or "").strip().lower())
            material_id = material.id if material else None
            resolved = resolve_material_norm(db, project.id, item.room_id, item.work_type_id, material_id, default_surface, norm)

            base_area = Decimal("0")
            for room in target_rooms:
                if resolved.unit_basis == "piece":
                    continue
                area, ok = _resolve_area_for_surface(room, resolved.surface_kind)
                if not ok:
                    warnings.append(f"room:{room.id}:MISSING_GEOMETRY:{resolved.surface_kind}")
                    continue
                base_area += area

            if resolved.unit_basis == "piece":
                measure = Decimal(str(item.quantity or 0))
            elif resolved.unit_basis == "room":
                measure = Decimal(len(target_rooms))
            else:
                measure = base_area

            if measure <= 0:
                continue
            per_basis_qty = Decimal(str(norm.per_basis_qty or resolved.base_unit_size or 1))
            consumption_qty = Decimal(str(norm.consumption_qty or norm.quantity_per_basis or resolved.quantity_per_unit or 0))
            if per_basis_qty <= 0:
                per_basis_qty = Decimal("1")
            qty = (measure / per_basis_qty) * consumption_qty

            coats = Decimal("1")
            if norm.layers_multiplier_enabled:
                coats_candidate = Decimal(str(item.quantity or 1))
                coats = coats_candidate if coats_candidate > 0 else Decimal("1")
            if (norm.coats_multiplier_mode or "").strip().lower() in {"use_work_coats", "use_work_item_quantity"}:
                coats_candidate = Decimal(str(item.quantity or 1))
                coats = coats_candidate if coats_candidate > 0 else Decimal("1")
            qty = _q(qty * coats)
            waste_pct = Decimal(str(norm.waste_factor_pct if norm.waste_factor_pct is not None else resolved.waste_percent))
            qty = _q(qty * (Decimal("1") + waste_pct / Decimal("100")))

            pack_size = Decimal(str(norm.package_size)) if norm.package_size is not None else None
            if (pack_size is None or pack_size <= 0) and catalog is not None and catalog.package_size is not None:
                pack_size = Decimal(str(catalog.package_size))
            packs_count = None
            qty_final = qty
            if pack_size is not None and pack_size > 0:
                packs_count = int((qty / pack_size).to_integral_value(rounding="ROUND_CEILING"))

            unit_price = Decimal(str(norm.default_unit_price_sek or 0))
            cost = _qm((Decimal(packs_count) * unit_price) if packs_count is not None else (qty_final * unit_price))
            basis_label = {"m2": "m2", "piece": "pcs", "room": "room"}.get(resolved.unit_basis, resolved.unit_basis)
            norm_label = f"{consumption_qty} / {per_basis_qty} {basis_label}"

            material_key = f"M:{material_id}" if material_id is not None else f"N:{norm.material_name}|{norm.material_unit}"
            key = material_key
            bucket = grouped.setdefault(
                key,
                {
                    "area": Decimal("0"),
                    "qty_required": Decimal("0"),
                    "qty_final": Decimal("0"),
                    "cost": Decimal("0"),
                    "packs": 0,
                    "has_packs": False,
                    "pack_size": pack_size,
                    "work_codes": set(),
                    "surface": resolved.surface_kind,
                    "coats": coats,
                    "norm": norm_label,
                    "waste": waste_pct,
                    "unit": norm.material_unit,
                    "material_name": display_name or norm.material_name,
                    "material_id": material_id,
                    "details": [],
                },
            )
            bucket["area"] += base_area
            bucket["qty_required"] += qty
            bucket["qty_final"] += qty_final
            bucket["cost"] += cost
            bucket["work_codes"].add(work_code)
            bucket["details"].append(BOMDetail(source="WORK_NORM", room_id=item.room_id, room_name=item.room.name if item.room else None, area_m2_used=_q(base_area), system_id=None, system_name=None, step_id=None, step_order=None, recipe_id=0))
            if packs_count is not None:
                bucket["has_packs"] = True
                bucket["packs"] += packs_count

    items: list[BOMItem] = []
    for idx, bucket in enumerate(grouped.values(), start=1):
        resolved_material_id = bucket.get("material_id")
        items.append(BOMItem(material_id=resolved_material_id if resolved_material_id is not None else -idx, name=bucket["material_name"], unit=bucket["unit"], area_m2_used=_q(bucket["area"]), qty_required_unit=_q(bucket["qty_required"]), packs_count=bucket["packs"] if bucket["has_packs"] else None, pack_size=bucket["pack_size"], qty_final_unit=_q(bucket["qty_final"]), cost_ex_vat=_qm(bucket["cost"]), sell_ex_vat=_qm(bucket["cost"]), details=bucket["details"], source_works=", ".join(sorted(bucket["work_codes"])), surface_type=bucket["surface"], coats=bucket["coats"], norm_label=bucket["norm"], waste_percent=bucket["waste"]))
    return items


def _area_by_basis(areas, basis: str) -> Decimal:
    if basis == "WALL_AREA":
        return Decimal(str(areas.total_wall_m2))
    if basis == "CEILING_AREA":
        return Decimal(str(areas.total_ceiling_m2))
    if basis == "PAINTABLE_TOTAL":
        return Decimal(str(areas.total_paintable_m2))
    return Decimal(str(areas.total_floor_m2))




def _line_from_qty(material, recipe: MaterialRecipe, settings: ProjectMaterialSettings, qty_required: Decimal, area: Decimal, details: list[BOMDetail], warnings: list[str]) -> BOMItem:
    pack_size = Decimal(str(recipe.pack_size_override)) if recipe.pack_size_override is not None else (
        Decimal(str(material.default_pack_size)) if material.default_pack_size is not None else None
    )
    packs_count: int | None = None
    qty_final = qty_required
    if recipe.rounding_mode == "CEIL_TO_PACKS":
        if pack_size is None or pack_size <= 0:
            warnings.append(f"recipe:{recipe.id}:MISSING_PACK_SIZE")
        else:
            packs_count = int((qty_required / pack_size).to_integral_value(rounding="ROUND_CEILING"))
            qty_final = _q(Decimal(packs_count) * pack_size)

    cost_unit = Decimal(str(material.default_cost_per_unit_ex_vat or 0))
    sell_unit = Decimal(str(material.default_sell_per_unit_ex_vat or 0))
    if sell_unit <= 0:
        markup_pct = Decimal(str(material.default_markup_pct if material.default_markup_pct is not None else settings.default_markup_pct))
        sell_unit = cost_unit * (Decimal("1") + markup_pct / Decimal("100"))

    cost = _qm(qty_final * cost_unit)
    sell = _qm(qty_final * sell_unit)
    return BOMItem(
        material_id=material.id,
        name=material.name_sv,
        unit=material.unit,
        area_m2_used=_q(area),
        qty_required_unit=qty_required,
        packs_count=packs_count,
        pack_size=pack_size,
        qty_final_unit=qty_final,
        cost_ex_vat=cost,
        sell_ex_vat=sell,
        details=details,
    )


def _surface_area_for_room(room: Room, surface: PaintSystemSurface) -> Decimal:
    floor = Decimal(str(room.floor_area_m2 or 0))
    wall = Decimal(str(room.wall_area_m2 or 0))
    if wall <= 0:
        wall = Decimal(str(room.wall_perimeter_m or 0)) * Decimal(str(room.wall_height_m or 0))
    ceiling = Decimal(str(room.ceiling_area_m2 or 0))
    if ceiling <= 0:
        ceiling = floor
    if surface == PaintSystemSurface.WALLS:
        return wall
    if surface == PaintSystemSurface.CEILING:
        return ceiling if ceiling > 0 else floor
    if surface == PaintSystemSurface.FLOOR:
        return floor
    return wall + ceiling


def _compute_bom_from_paint_systems(db: Session, project: Project, settings: ProjectMaterialSettings, warnings: list[str]) -> list[BOMItem]:
    project_paint = db.query(ProjectPaintSettings).filter(ProjectPaintSettings.project_id == project.id).first()
    if not project_paint:
        return []
    rooms = db.query(Room).filter(Room.project_id == project.id).all()
    if not rooms:
        return []

    room_settings_map = {rps.room_id: rps for rps in db.query(RoomPaintSettings).filter(RoomPaintSettings.room_id.in_([r.id for r in rooms])).all()}
    source_lines: list[tuple[MaterialRecipe, Decimal, Decimal, list[BOMDetail]]] = []
    applied_steps: set[tuple[int, int, int]] = set()
    for room in rooms:
        rps = room_settings_map.get(room.id)
        wall_system = (rps.wall_paint_system if rps and rps.wall_paint_system_id else None) or project_paint.default_wall_paint_system
        ceiling_system = (rps.ceiling_paint_system if rps and rps.ceiling_paint_system_id else None) or project_paint.default_ceiling_paint_system
        for system in [s for s in [wall_system, ceiling_system] if s]:
            for step in sorted(system.steps, key=lambda x: x.step_order):
                stamp = (room.id, system.id, step.id)
                if stamp in applied_steps:
                    continue
                applied_steps.add(stamp)
                area = _surface_area_for_room(room, step.target_surface)
                if area <= 0:
                    continue
                recipe = step.recipe
                consumption = Decimal(str(recipe.consumption_per_m2 or 0))
                coats = Decimal(str(step.override_coats_count if step.override_coats_count is not None else recipe.coats_count or 1))
                waste_pct = Decimal(str(step.override_waste_pct if step.override_waste_pct is not None else recipe.waste_pct or 0))
                qty_required = _q(area * consumption * coats * (Decimal("1") + waste_pct / Decimal("100")))
                source_lines.append((recipe, qty_required, area, [BOMDetail(source="PAINT_SYSTEM", room_id=room.id, room_name=room.name, area_m2_used=_q(area), system_id=system.id, system_name=f"{system.name} v{system.version}", step_id=step.id, step_order=step.step_order, recipe_id=recipe.id)]))

    grouped: dict[int, dict] = {}
    for recipe, qty_required, area, details in source_lines:
        mid = recipe.material_id
        bucket = grouped.setdefault(mid, {"recipe": recipe, "qty": Decimal("0"), "area": Decimal("0"), "details": []})
        bucket["qty"] += qty_required
        bucket["area"] += area
        bucket["details"].extend(details)

    items: list[BOMItem] = []
    for bucket in grouped.values():
        recipe = bucket["recipe"]
        items.append(_line_from_qty(recipe.material, recipe, settings, _q(bucket["qty"]), _q(bucket["area"]), bucket["details"], warnings))
    return items

def _compute_bom_from_legacy_recipes(db: Session, project: Project, settings: ProjectMaterialSettings, areas, warnings: list[str]) -> list[BOMItem]:
    work_type_ids = {wi.work_type_id for wi in project.work_items}
    recipes = db.query(MaterialRecipe).filter(MaterialRecipe.is_active.is_(True)).all()
    items: list[BOMItem] = []
    for recipe in recipes:
        if recipe.applies_to == "WORKTYPE" and recipe.work_type_id not in work_type_ids:
            continue
        area = _area_by_basis(areas, recipe.basis)
        consumption = Decimal(str(recipe.consumption_per_m2 or 0))
        coats = Decimal(str(recipe.coats_count or 1))
        waste_pct = Decimal(str(recipe.waste_pct or 0))
        qty = _q(area * consumption * coats * (Decimal("1") + waste_pct / Decimal("100")))
        items.append(_line_from_qty(recipe.material, recipe, settings, qty, area, [BOMDetail(source="LEGACY_RECIPE", room_id=None, room_name=None, area_m2_used=_q(area), system_id=None, system_name=None, step_id=None, step_order=None, recipe_id=recipe.id)], warnings))
    return items


def compute_project_bom(db: Session, project_id: int, *, cache: RequestCache | None = None) -> BOMReport:
    key = cache_key("materials_bom", project_id)
    if cache is not None:
        cached = cache.get(key)
        if cached is not None:
            return cached

    project = (
        db.query(Project)
        .options(joinedload(Project.work_items).joinedload(ProjectWorkItem.work_type), joinedload(Project.work_items).joinedload(ProjectWorkItem.room))
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise ValueError("Project not found")

    takeoff = get_or_create_project_takeoff_settings(db, project_id)
    areas = compute_project_areas(db, project_id, cache=cache)
    settings = get_or_create_project_material_settings(db, project_id)
    warnings: list[str] = []

    items = _compute_bom_from_norms(db, project, warnings)
    if not items:
        items = _compute_bom_from_paint_systems(db, project, settings, warnings)
    if not items:
        items = _compute_bom_from_legacy_recipes(db, project, settings, areas, warnings)

    total_cost = sum((item.cost_ex_vat for item in items), start=Decimal("0"))
    total_sell = sum((item.sell_ex_vat for item in items), start=Decimal("0"))
    result = BOMReport(
        basis_used=takeoff.m2_basis,
        total_floor_m2=Decimal(str(areas.total_floor_m2)),
        total_wall_m2=Decimal(str(areas.total_wall_m2)),
        total_ceiling_m2=Decimal(str(areas.total_ceiling_m2)),
        total_paintable_m2=Decimal(str(areas.total_paintable_m2)),
        items=sorted(items, key=lambda x: x.name.lower()),
        total_cost_ex_vat=_qm(total_cost),
        total_sell_ex_vat=_qm(total_sell),
        warnings=sorted(set(warnings)),
    )
    if cache is not None:
        cache.set(key, result)
    return result


def apply_bom_to_project_cost_items(db: Session, project_id: int, report: BOMReport) -> int:
    category = db.query(CostCategory).filter(CostCategory.code == "MATERIALS").first()
    if category is None:
        category = CostCategory(code="MATERIALS", name_ru="Материалы", name_sv="Material")
        db.add(category)
        db.flush()
    added = 0
    for item in report.items:
        db.add(ProjectCostItem(project_id=project_id, cost_category_id=category.id, material_id=item.material_id if item.material_id > 0 else None, title=f"BOM: {item.name}", amount=item.cost_ex_vat, is_material=True, comment=f"qty={item.qty_final_unit} {item.unit}"))
        added += 1
    db.commit()
    return added


def apply_bom_to_invoice_material_lines(db: Session, project_id: int, report: BOMReport) -> int:
    from app.services.invoice_lines import recalculate_invoice_totals

    invoice = db.query(Invoice).filter(Invoice.project_id == project_id, Invoice.status == "draft").order_by(Invoice.id.desc()).first()
    if invoice is None:
        raise ValueError("Draft invoice not found")

    position = len(invoice.lines) + 1
    for item in report.items:
        db.add(InvoiceLine(invoice_id=invoice.id, position=position, kind="MATERIAL", description=f"BOM: {item.name}", unit=item.unit, quantity=_q(item.qty_final_unit, Decimal("0.01")), unit_price_ex_vat=_q((item.sell_ex_vat / item.qty_final_unit) if item.qty_final_unit > 0 else Decimal("0"), Decimal("0.01")), vat_rate_pct=Decimal("25.00"), source_type="BOM", source_id=item.material_id if item.material_id > 0 else None))
        position += 1

    db.flush()
    recalculate_invoice_totals(db, invoice)
    db.commit()
    return len(report.items)


def _select_supplier_price(*, prices: list[SupplierMaterialPrice], strategy: ProcurementStrategy, supplier_id: int | None) -> SupplierMaterialPrice | None:
    if not prices:
        return None
    sorted_prices = sorted(prices, key=lambda p: (Decimal(str(p.pack_price_ex_vat or 0)), p.supplier_id, p.id))
    if strategy == ProcurementStrategy.FIXED_SUPPLIER:
        return next((p for p in sorted_prices if p.supplier_id == supplier_id), None)
    if strategy == ProcurementStrategy.PREFERRED_FIRST and supplier_id:
        preferred = next((p for p in sorted_prices if p.supplier_id == supplier_id), None)
        if preferred:
            return preferred
    return sorted_prices[0]


def compute_procurement_plan(
    db: Session,
    project_id: int,
    strategy: ProcurementStrategy = ProcurementStrategy.CHEAPEST,
    supplier_id: int | None = None,
    policy: ProcurementRoundingPolicy | None = None,
    cache: RequestCache | None = None,
) -> ProcurementPlan:
    bom = compute_project_bom(db, project_id, cache=cache)
    resolved_policy = normalize_policy(policy)
    lines: list[ProcurementLine] = []
    warnings: list[str] = []

    material_ids = [item.material_id for item in bom.items]
    supplier_prices = (
        db.query(SupplierMaterialPrice)
        .options(joinedload(SupplierMaterialPrice.supplier))
        .filter(SupplierMaterialPrice.material_id.in_(material_ids))
        .all()
        if material_ids
        else []
    )
    prices_by_material: dict[int, list[SupplierMaterialPrice]] = {}
    for price in supplier_prices:
        prices_by_material.setdefault(price.material_id, []).append(price)

    materials = db.query(Material).filter(Material.id.in_(material_ids)).all() if material_ids else []
    materials_by_id = {material.id: material for material in materials}
    material_codes = sorted({(material.code or "").strip() for material in materials if (material.code or "").strip()})
    catalog_items = (
        db.query(MaterialCatalogItem)
        .filter(MaterialCatalogItem.material_code.in_(material_codes), MaterialCatalogItem.is_active.is_(True))
        .all()
        if material_codes
        else []
    )
    catalog_by_code: dict[str, list[MaterialCatalogItem]] = {}
    for catalog in catalog_items:
        code = (catalog.material_code or "").strip()
        if code:
            catalog_by_code.setdefault(code, []).append(catalog)

    for item in bom.items:
        line_warnings: list[str] = []
        prices = prices_by_material.get(item.material_id, [])
        selected = _select_supplier_price(prices=prices, strategy=strategy, supplier_id=supplier_id)
        qty = Decimal(str(item.qty_final_unit or 0))
        packs_needed: Decimal | None = Decimal("0")
        purchase_qty = qty
        line_total = Decimal("0")
        unit_price = None
        price_unit = None
        supplier_name = selected.supplier.name if selected else None
        if selected is None:
            material = materials_by_id.get(item.material_id)
            catalog_selected: MaterialCatalogItem | None = None
            if material is not None:
                catalog_prices = catalog_by_code.get((material.code or "").strip(), [])
                default_prices = [catalog for catalog in catalog_prices if catalog.is_default_for_material]
                price_pool = default_prices or catalog_prices
                if price_pool:
                    catalog_selected = min(
                        price_pool,
                        key=lambda catalog: Decimal(str(catalog.price_ex_vat or 0)) / Decimal(str(catalog.package_size or 1)),
                    )

            if catalog_selected is None:
                line_warnings.append("NO_SUPPLIER_PRICE")
                line_total = _qm(Decimal(str(item.cost_ex_vat or 0)))
            else:
                pack_size = Decimal(str(catalog_selected.package_size or 0))
                if pack_size <= 0:
                    line_warnings.append("NO_PACK_SIZE")
                    line_warnings.append("INVALID_PACK_SIZE")
                    line_total = _qm(Decimal(str(item.cost_ex_vat or 0)))
                else:
                    try:
                        qty_in_pack_unit = convert_qty(qty, item.unit, catalog_selected.package_unit)
                        packs_needed = compute_packs_needed(qty_in_pack_unit, pack_size, resolved_policy)
                        purchase_qty = packs_needed * pack_size
                        unit_price = Decimal(str(catalog_selected.price_ex_vat or 0))
                        price_unit = "PACK"
                        line_total = _qm(packs_needed * unit_price)
                        supplier_name = (catalog_selected.supplier_name or "Catalog").strip() or "Catalog"
                        line_warnings.append("CATALOG_PRICE_USED")
                    except UnitConversionError as exc:
                        packs_needed = None
                        purchase_qty = Decimal("0")
                        unit_price = None
                        line_total = Decimal("0")
                        source_unit = normalize_unit(item.unit) or (item.unit or "")
                        target_unit = normalize_unit(catalog_selected.package_unit) or (catalog_selected.package_unit or "")
                        line_warnings.append(f"{exc.code}:{source_unit}->{target_unit}")
        else:
            pack_size = Decimal(str(selected.pack_size or 0))
            if pack_size <= 0:
                line_warnings.append("NO_PACK_SIZE")
                line_warnings.append("INVALID_PACK_SIZE")
                line_total = _qm(Decimal(str(item.cost_ex_vat or 0)))
            else:
                try:
                    qty_in_pack_unit = convert_qty(qty, item.unit, selected.pack_unit)
                    packs_needed = compute_packs_needed(qty_in_pack_unit, pack_size, resolved_policy)
                    purchase_qty = packs_needed * pack_size
                    unit_price = Decimal(str(selected.pack_price_ex_vat or 0))
                    price_unit = "PACK"
                    line_total = _qm(packs_needed * unit_price)
                except UnitConversionError as exc:
                    packs_needed = None
                    purchase_qty = Decimal("0")
                    unit_price = None
                    line_total = Decimal("0")
                    source_unit = normalize_unit(item.unit) or (item.unit or "")
                    target_unit = normalize_unit(selected.pack_unit) or (selected.pack_unit or "")
                    line_warnings.append(f"{exc.code}:{source_unit}->{target_unit}")
        line_warnings = sorted(set(line_warnings))
        if line_warnings:
            warnings.extend([f"material:{item.material_id}:{code}" for code in line_warnings])
        lines.append(
            ProcurementLine(
                material_id=item.material_id,
                material_name=item.name,
                qty=qty,
                unit=item.unit,
                supplier_id=selected.supplier_id if selected else None,
                supplier_name=supplier_name,
                price_unit=price_unit,
                unit_price_ex_vat=unit_price,
                packs_needed=packs_needed,
                purchase_qty=_q(purchase_qty),
                line_total_cost_ex_vat=line_total,
                warnings=line_warnings,
            )
        )
    total = _qm(sum((line.line_total_cost_ex_vat for line in lines), Decimal("0")))
    return ProcurementPlan(strategy=strategy, lines=lines, total_cost_ex_vat=total, warnings=sorted(set(warnings)))
