from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.material_catalog_item import MaterialCatalogItem
from app.services.materials_consumption import MaterialNeedTotal, calculate_material_needs_for_project

MONEY_Q = Decimal("0.01")
QTY_Q = Decimal("0.0001")
VALID_UNITS = {"l", "kg", "m2", "pcs", "roll", "bucket"}


@dataclass
class MaterialCostRow:
    material_code: str
    material_name: str
    required_quantity: Decimal
    required_unit: str
    selected_catalog_item_id: int | None
    package_size: Decimal | None
    package_unit: str | None
    packages_to_buy: int
    purchasable_quantity: Decimal
    overbuy_quantity: Decimal
    unit_price_ex_vat: Decimal
    total_ex_vat: Decimal
    total_vat: Decimal
    total_inc_vat: Decimal
    warnings: list[str]


@dataclass
class MaterialCostReport:
    project_id: int
    rows: list[MaterialCostRow]
    total_ex_vat: Decimal
    total_vat: Decimal
    total_inc_vat: Decimal
    unresolved_rows: list[MaterialCostRow]


def _qm(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _qq(value: Decimal) -> Decimal:
    return value.quantize(QTY_Q, rounding=ROUND_HALF_UP)


def _material_code(total: MaterialNeedTotal) -> str:
    return total.material_name.strip().lower().replace(" ", "_")


def _compatible_unit(required_unit: str, package_unit: str) -> bool:
    return (required_unit or "").strip().lower() == (package_unit or "").strip().lower()


def _resolve_catalog_item(db: Session, material_code: str) -> MaterialCatalogItem | None:
    items = db.query(MaterialCatalogItem).filter(MaterialCatalogItem.material_code == material_code, MaterialCatalogItem.is_active.is_(True)).all()
    if not items:
        return None
    defaults = [i for i in items if i.is_default_for_material]
    pool = defaults or items

    def _score(item: MaterialCatalogItem) -> tuple[Decimal, int]:
        per_unit = Decimal(str(item.price_ex_vat or 0)) / Decimal(str(item.package_size or 1))
        return (per_unit, item.id)

    return sorted(pool, key=_score)[0]


def cost_material_rows(db: Session, totals: list[MaterialNeedTotal]) -> list[MaterialCostRow]:
    rows: list[MaterialCostRow] = []
    for total in totals:
        required_qty = Decimal(str(total.total_quantity or 0))
        required_unit = (total.material_unit or "").lower()
        material_code = _material_code(total)
        warnings: list[str] = []
        item = _resolve_catalog_item(db, material_code)
        if item is None:
            warnings.append("UNRESOLVED_PRICING")
            rows.append(MaterialCostRow(material_code=material_code, material_name=total.material_name, required_quantity=_qq(required_qty), required_unit=required_unit, selected_catalog_item_id=None, package_size=None, package_unit=None, packages_to_buy=0, purchasable_quantity=Decimal("0"), overbuy_quantity=Decimal("0"), unit_price_ex_vat=Decimal("0"), total_ex_vat=Decimal("0"), total_vat=Decimal("0"), total_inc_vat=Decimal("0"), warnings=warnings))
            continue

        package_unit = (item.package_unit or "").lower()
        if not _compatible_unit(required_unit, package_unit):
            warnings.append("UNIT_MISMATCH")
            rows.append(MaterialCostRow(material_code=material_code, material_name=total.material_name, required_quantity=_qq(required_qty), required_unit=required_unit, selected_catalog_item_id=item.id, package_size=Decimal(str(item.package_size)), package_unit=package_unit, packages_to_buy=0, purchasable_quantity=Decimal("0"), overbuy_quantity=Decimal("0"), unit_price_ex_vat=Decimal(str(item.price_ex_vat or 0)), total_ex_vat=Decimal("0"), total_vat=Decimal("0"), total_inc_vat=Decimal("0"), warnings=warnings))
            continue

        package_size = Decimal(str(item.package_size))
        packages = int((required_qty / package_size).to_integral_value(rounding=ROUND_CEILING)) if required_qty > 0 else 0
        purchasable_qty = _qq(Decimal(packages) * package_size)
        overbuy = _qq(purchasable_qty - required_qty)
        total_ex = _qm(Decimal(packages) * Decimal(str(item.price_ex_vat or 0)))
        vat = _qm(total_ex * Decimal(str(item.vat_rate_pct or 0)) / Decimal("100"))
        rows.append(MaterialCostRow(material_code=material_code, material_name=total.material_name, required_quantity=_qq(required_qty), required_unit=required_unit, selected_catalog_item_id=item.id, package_size=package_size, package_unit=package_unit, packages_to_buy=packages, purchasable_quantity=purchasable_qty, overbuy_quantity=overbuy, unit_price_ex_vat=Decimal(str(item.price_ex_vat or 0)), total_ex_vat=total_ex, total_vat=vat, total_inc_vat=_qm(total_ex + vat), warnings=warnings))
    return rows


def cost_project_materials(db: Session, project_id: int) -> MaterialCostReport:
    _, totals = calculate_material_needs_for_project(db, project_id)
    rows = cost_material_rows(db, totals)
    total_ex = _qm(sum((r.total_ex_vat for r in rows), Decimal("0")))
    total_vat = _qm(sum((r.total_vat for r in rows), Decimal("0")))
    unresolved = [r for r in rows if r.warnings]
    return MaterialCostReport(project_id=project_id, rows=rows, total_ex_vat=total_ex, total_vat=total_vat, total_inc_vat=_qm(total_ex + total_vat), unresolved_rows=unresolved)


def build_project_shopping_list(db: Session, project_id: int) -> MaterialCostReport:
    return cost_project_materials(db, project_id)
