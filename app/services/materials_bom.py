from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.cost import CostCategory, ProjectCostItem
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.material_recipe import MaterialRecipe
from app.models.project import Project
from app.models.project_material_settings import ProjectMaterialSettings
from app.services.takeoff import compute_project_areas, get_or_create_project_takeoff_settings


UNIT_Q = Decimal("0.0001")
MONEY_Q = Decimal("0.01")


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


def _area_by_basis(areas, basis: str) -> Decimal:
    if basis == "WALL_AREA":
        return Decimal(str(areas.total_wall_m2))
    if basis == "CEILING_AREA":
        return Decimal(str(areas.total_ceiling_m2))
    if basis == "PAINTABLE_TOTAL":
        return Decimal(str(areas.total_paintable_m2))
    return Decimal(str(areas.total_floor_m2))


def compute_project_bom(db: Session, project_id: int) -> BOMReport:
    project = db.get(Project, project_id)
    if not project:
        raise ValueError("Project not found")

    takeoff = get_or_create_project_takeoff_settings(db, project_id)
    settings = get_or_create_project_material_settings(db, project_id)
    areas = compute_project_areas(db, project_id)
    warnings: list[str] = []

    work_type_ids = {wi.work_type_id for wi in project.work_items}
    recipes = db.query(MaterialRecipe).filter(MaterialRecipe.is_active.is_(True)).all()
    applicable: list[MaterialRecipe] = []
    for recipe in recipes:
        if recipe.applies_to == "PROJECT":
            applicable.append(recipe)
        elif recipe.applies_to == "WORKTYPE" and recipe.work_type_id in work_type_ids:
            applicable.append(recipe)

    picked: dict[tuple[int, str, int | None, str], MaterialRecipe] = {}
    for recipe in applicable:
        key = (recipe.material_id, recipe.applies_to, recipe.work_type_id, recipe.basis)
        current = picked.get(key)
        if current is None or int(recipe.priority or 0) > int(current.priority or 0):
            picked[key] = recipe

    items: list[BOMItem] = []
    total_cost = Decimal("0")
    total_sell = Decimal("0")

    for recipe in picked.values():
        material = recipe.material
        area = _area_by_basis(areas, recipe.basis)
        if area <= 0:
            warnings.append(f"recipe:{recipe.id}:NO_AREAS_FOR_BASIS")
        consumption = Decimal(str(recipe.consumption_per_m2 or 0))
        coats = Decimal(str(recipe.coats_count or 1))
        waste_factor = Decimal("1") + (Decimal(str(recipe.waste_pct or 0)) / Decimal("100"))
        qty_required = _q(area * consumption * coats * waste_factor)

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

        if cost_unit <= 0:
            warnings.append(f"material:{material.id}:MISSING_COST")
        if sell_unit <= 0:
            warnings.append(f"material:{material.id}:MISSING_SELL")

        cost = _qm(qty_final * cost_unit)
        sell = _qm(qty_final * sell_unit)
        total_cost += cost
        total_sell += sell

        items.append(
            BOMItem(
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
            )
        )

    return BOMReport(
        basis_used=takeoff.m2_basis,
        total_floor_m2=Decimal(str(areas.total_floor_m2)),
        total_wall_m2=Decimal(str(areas.total_wall_m2)),
        total_ceiling_m2=Decimal(str(areas.total_ceiling_m2)),
        total_paintable_m2=Decimal(str(areas.total_paintable_m2)),
        items=sorted(items, key=lambda x: x.material_id),
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
    for item in report.items:
        db.add(
            ProjectCostItem(
                project_id=project_id,
                cost_category_id=category.id,
                material_id=item.material_id,
                title=f"BOM: {item.name}",
                amount=item.cost_ex_vat,
                is_material=True,
                comment=f"qty={item.qty_final_unit} {item.unit}",
            )
        )
    db.commit()
    return len(report.items)


def apply_bom_to_invoice_material_lines(db: Session, project_id: int, report: BOMReport) -> int:
    from app.services.invoice_lines import recalculate_invoice_totals

    invoice = (
        db.query(Invoice)
        .filter(Invoice.project_id == project_id, Invoice.status == "draft")
        .order_by(Invoice.id.desc())
        .first()
    )
    if invoice is None:
        raise ValueError("Draft invoice not found")

    position = len(invoice.lines) + 1
    for item in report.items:
        db.add(
            InvoiceLine(
                invoice_id=invoice.id,
                position=position,
                kind="MATERIAL",
                description=f"BOM: {item.name}",
                unit=item.unit,
                quantity=_q(item.qty_final_unit, Decimal("0.01")),
                unit_price_ex_vat=_q((item.sell_ex_vat / item.qty_final_unit) if item.qty_final_unit > 0 else Decimal("0"), Decimal("0.01")),
                vat_rate_pct=Decimal("25.00"),
                source_type="BOM",
                source_id=item.material_id,
            )
        )
        position += 1
    recalculate_invoice_totals(db, invoice.id)
    db.commit()
    return len(report.items)
