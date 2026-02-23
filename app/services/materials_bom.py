from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session, joinedload

from app.models.cost import CostCategory, ProjectCostItem
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.material_norm import MaterialConsumptionNorm
from app.models.material_recipe import MaterialRecipe
from app.models.paint_system import PaintSystemSurface, ProjectPaintSettings, RoomPaintSettings
from app.models.project import Project, ProjectWorkItem
from app.models.project_material_settings import ProjectMaterialSettings
from app.models.room import Room
from app.services.takeoff import compute_project_areas, get_or_create_project_takeoff_settings

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
    norm_by_work = {(n.applies_to_work_type or "").strip().lower(): n for n in norms}
    rooms = {r.id: r for r in db.query(Room).filter(Room.project_id == project.id).all()}
    if not rooms:
        return []

    grouped: dict[str, dict] = {}
    for item in project.work_items:
        work_code = (item.work_type.code or "").strip().lower()
        norm = norm_by_work.get(work_code)
        if norm is None:
            warnings.append(f"work:{work_code}:MISSING_NORM")
            continue

        target_rooms = [rooms[item.room_id]] if item.room_id in rooms else list(rooms.values())
        surface = norm.surface_type or _infer_surface_for_work(item)
        area = sum((_resolve_surface_area(room, surface) for room in target_rooms), start=Decimal("0"))
        if area <= 0:
            continue

        consumption_value = Decimal(str(norm.consumption_value or 0))
        if norm.consumption_unit == "per_10_m2":
            qty = (area / Decimal("10")) * consumption_value
            norm_label = f"{consumption_value} / 10 m2"
        else:
            qty = area * consumption_value
            norm_label = f"{consumption_value} / 1 m2"

        coats = Decimal("1")
        if norm.coats_multiplier_mode == "use_work_coats":
            coats = Decimal(str(item.quantity or 1)) if Decimal(str(item.quantity or 0)) > 0 else Decimal("1")
        qty = qty * coats

        waste_percent = Decimal(str(norm.waste_percent if norm.waste_percent is not None else 10))
        qty = qty * (Decimal("1") + waste_percent / Decimal("100"))
        qty = _q(qty)

        pack_size = Decimal(str(norm.package_size)) if norm.package_size is not None else None
        packs_count = None
        qty_final = qty
        if pack_size is not None and pack_size > 0:
            packs_count = int((qty / pack_size).to_integral_value(rounding="ROUND_CEILING"))
    
        unit_price = Decimal(str(norm.default_unit_price_sek or 0))
        cost = _qm((Decimal(packs_count) * unit_price) if packs_count is not None else (qty_final * unit_price))

        key = f"{norm.material_name}|{norm.material_unit}"
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
                "surface": surface,
                "coats": coats,
                "norm": norm_label,
                "waste": waste_percent,
                "unit": norm.material_unit,
                "material_name": norm.material_name,
                "details": [],
            },
        )
        bucket["area"] += area
        bucket["qty_required"] += qty
        bucket["qty_final"] += qty_final
        bucket["cost"] += cost
        bucket["work_codes"].add(work_code)
        bucket["details"].append(BOMDetail(source="WORK_NORM", room_id=item.room_id, room_name=item.room.name if item.room else None, area_m2_used=_q(area), system_id=None, system_name=None, step_id=None, step_order=None, recipe_id=0))
        if packs_count is not None:
            bucket["has_packs"] = True
            bucket["packs"] += packs_count

    items: list[BOMItem] = []
    for idx, bucket in enumerate(grouped.values(), start=1):
        items.append(BOMItem(material_id=-idx, name=bucket["material_name"], unit=bucket["unit"], area_m2_used=_q(bucket["area"]), qty_required_unit=_q(bucket["qty_required"]), packs_count=bucket["packs"] if bucket["has_packs"] else None, pack_size=bucket["pack_size"], qty_final_unit=_q(bucket["qty_final"]), cost_ex_vat=_qm(bucket["cost"]), sell_ex_vat=_qm(bucket["cost"]), details=bucket["details"], source_works=", ".join(sorted(bucket["work_codes"])), surface_type=bucket["surface"], coats=bucket["coats"], norm_label=bucket["norm"], waste_percent=bucket["waste"]))
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


def compute_project_bom(db: Session, project_id: int) -> BOMReport:
    project = (
        db.query(Project)
        .options(joinedload(Project.work_items).joinedload(ProjectWorkItem.work_type), joinedload(Project.work_items).joinedload(ProjectWorkItem.room))
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise ValueError("Project not found")

    takeoff = get_or_create_project_takeoff_settings(db, project_id)
    areas = compute_project_areas(db, project_id)
    settings = get_or_create_project_material_settings(db, project_id)
    warnings: list[str] = []

    items = _compute_bom_from_norms(db, project, warnings)
    if not items:
        items = _compute_bom_from_paint_systems(db, project, settings, warnings)
    if not items:
        items = _compute_bom_from_legacy_recipes(db, project, settings, areas, warnings)

    total_cost = sum((item.cost_ex_vat for item in items), start=Decimal("0"))
    total_sell = sum((item.sell_ex_vat for item in items), start=Decimal("0"))
    return BOMReport(
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
