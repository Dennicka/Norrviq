import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.cost import CostCategory, ProjectCostItem
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.material import Material
from app.models.project_procurement_settings import ProjectProcurementSettings
from app.models.supplier_material_price import SupplierMaterialPrice
from app.services.invoice_lines import recalculate_invoice_totals
from app.services.materials_bom import compute_project_bom

MONEY_Q = Decimal("0.01")


@dataclass
class ShoppingListItem:
    material_id: int
    material_name: str
    planned_qty: Decimal
    planned_unit: str
    pack_size: Decimal | None
    pack_unit: str | None
    packs_needed: Decimal
    purchase_qty: Decimal
    supplier_id: int | None
    supplier_name: str | None
    unit_price: Decimal | None
    line_total_cost: Decimal
    warnings: list[str]
    sku: str | None = None

    @property
    def qty_final_unit(self) -> Decimal:
        return self.planned_qty

    @property
    def unit(self) -> str:
        return self.planned_unit

    @property
    def packs_count(self) -> Decimal:
        return self.packs_needed

    @property
    def pack_price_ex_vat(self) -> Decimal:
        return self.unit_price or Decimal("0")

    @property
    def total_ex_vat(self) -> Decimal:
        return self.line_total_cost

    @property
    def estimated_cost_inc_vat(self) -> Decimal:
        return self.line_total_cost

    @property
    def vat_rate_pct(self) -> Decimal:
        return Decimal("25.00")

    @property
    def notes(self) -> str | None:
        return ",".join(self.warnings) if self.warnings else None

    @property
    def cost_ex_vat(self) -> Decimal:
        return self.line_total_cost


@dataclass
class ShoppingListReport:
    project_id: int
    source_hash: str
    items: list[ShoppingListItem]
    total_packs: Decimal
    total_cost_sek: Decimal
    grouped_by_supplier: dict[str, list[ShoppingListItem]]
    warnings: list[str]

    @property
    def total_ex_vat(self) -> Decimal:
        return self.total_cost_sek

    @property
    def total_inc_vat(self) -> Decimal:
        return self.total_cost_sek


def _qm(v: Decimal) -> Decimal:
    return v.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def get_or_create_procurement_settings(db: Session, project_id: int) -> ProjectProcurementSettings:
    settings = db.query(ProjectProcurementSettings).filter_by(project_id=project_id).first()
    if settings:
        return settings
    settings = ProjectProcurementSettings(project_id=project_id)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def _select_price(prices: list[SupplierMaterialPrice], supplier_id: int | None, preferred_supplier_id: int | None, auto_select_cheapest: bool) -> SupplierMaterialPrice | None:
    if not prices:
        return None
    if supplier_id:
        for price in prices:
            if price.supplier_id == supplier_id:
                return price
        return None
    if preferred_supplier_id:
        for price in prices:
            if price.supplier_id == preferred_supplier_id:
                return price
    if auto_select_cheapest:
        def _unit_price(p: SupplierMaterialPrice) -> Decimal:
            pack_size = Decimal(str(p.pack_size or 0))
            pack_price = Decimal(str(p.pack_price_ex_vat or 0))
            if pack_size <= 0:
                return Decimal("Infinity")
            return pack_price / pack_size

        return min(
            prices,
            key=lambda p: (
                _unit_price(p),
                Decimal(str(p.pack_price_ex_vat or 0)),
                p.supplier_id,
                p.id,
            ),
        )
    return min(prices, key=lambda p: (p.supplier_id, p.id))


def _round_packs(planned_qty: Decimal, pack_size: Decimal, rounding_rule: str, min_pack_qty: Decimal) -> Decimal:
    ratio = planned_qty / pack_size
    if rounding_rule == "NONE":
        packs = ratio
    elif rounding_rule == "NEAREST":
        packs = ratio.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    else:
        packs = ratio.to_integral_value(rounding=ROUND_CEILING)
    return packs if packs >= min_pack_qty else min_pack_qty


def compute_project_shopping_list(
    db: Session,
    project_id: int,
    supplier_id: int | None = None,
    group_by_supplier: bool = True,
    include_items_without_price: bool = True,
) -> ShoppingListReport:
    bom = compute_project_bom(db, project_id)
    settings = get_or_create_procurement_settings(db, project_id)
    warnings: list[str] = []
    items: list[ShoppingListItem] = []

    for bom_item in bom.items:
        planned_qty = Decimal(str(bom_item.qty_final_unit or 0))
        if planned_qty <= 0:
            continue
        material = db.get(Material, bom_item.material_id)
        prices = db.query(SupplierMaterialPrice).filter(SupplierMaterialPrice.material_id == bom_item.material_id).all()
        selected_price = _select_price(prices, supplier_id, settings.preferred_supplier_id, settings.auto_select_cheapest)

        pack_size = Decimal(str(selected_price.pack_size)) if selected_price and selected_price.pack_size else None
        pack_unit = selected_price.pack_unit if selected_price else None
        if pack_size is None and material and material.pack_size is not None:
            pack_size = Decimal(str(material.pack_size))
            pack_unit = material.pack_unit or bom_item.unit
        rounding_rule = str((material.pack_rounding_rule if material else "CEIL") or "CEIL")
        min_pack_qty = Decimal(str((material.min_pack_qty if material else 1) or 1))

        line_warnings: list[str] = []
        if pack_size is None or pack_size <= 0:
            packs_needed = planned_qty
            purchase_qty = planned_qty
            pack_size = None
            line_warnings.append("NO_PACK_SIZE")
        else:
            packs_needed = _round_packs(planned_qty, pack_size, rounding_rule, min_pack_qty)
            purchase_qty = _qm(packs_needed * pack_size)

        unit_price = Decimal(str(selected_price.price_per_pack)) if selected_price else None
        if unit_price is None:
            line_warnings.append("NO_SUPPLIER_PRICE")
            if not include_items_without_price:
                continue

        line_total = _qm((unit_price or Decimal("0")) * packs_needed)
        for code in line_warnings:
            warnings.append(f"material:{bom_item.material_id}:{code}")

        items.append(
            ShoppingListItem(
                material_id=bom_item.material_id,
                material_name=bom_item.name,
                planned_qty=planned_qty,
                planned_unit=bom_item.unit,
                pack_size=pack_size,
                pack_unit=pack_unit or bom_item.unit,
                packs_needed=packs_needed,
                purchase_qty=purchase_qty,
                supplier_id=selected_price.supplier_id if selected_price else None,
                supplier_name=selected_price.supplier.name if selected_price else None,
                unit_price=unit_price,
                line_total_cost=line_total,
                warnings=line_warnings,
            )
        )

    items = sorted(items, key=lambda i: (i.material_name.lower(), i.material_id))
    grouped: dict[str, list[ShoppingListItem]] = {}
    if group_by_supplier:
        for item in items:
            key = item.supplier_name or "Unassigned"
            grouped.setdefault(key, []).append(item)

    total_packs = _qm(sum((item.packs_needed for item in items), start=Decimal("0")))
    total_cost = _qm(sum((item.line_total_cost for item in items), start=Decimal("0")))
    payload = {
        "project_id": project_id,
        "supplier_id": supplier_id,
        "group_by_supplier": group_by_supplier,
        "include_items_without_price": include_items_without_price,
        "items": [{**asdict(item), "planned_qty": str(item.planned_qty), "pack_size": str(item.pack_size) if item.pack_size is not None else None, "packs_needed": str(item.packs_needed)} for item in items],
        "totals": {"packs": str(total_packs), "cost": str(total_cost)},
    }
    source_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return ShoppingListReport(project_id=project_id, source_hash=source_hash, items=items, total_packs=total_packs, total_cost_sek=total_cost, grouped_by_supplier=grouped, warnings=sorted(set(warnings)))


def apply_shopping_list_to_project_cost_items(db: Session, project_id: int, report: ShoppingListReport) -> int:
    existing = db.query(ProjectCostItem).filter_by(project_id=project_id, source_type="SHOPPING_LIST", source_hash=report.source_hash).first()
    if existing:
        raise ValueError("already applied")
    category = db.query(CostCategory).filter(CostCategory.code == "MATERIALS").first()
    if not category:
        category = CostCategory(code="MATERIALS", name_ru="Материалы", name_sv="Material")
        db.add(category)
        db.flush()
    for item in report.items:
        db.add(ProjectCostItem(project_id=project_id, cost_category_id=category.id, material_id=item.material_id, title=f"Shopping: {item.material_name}", amount=item.line_total_cost, is_material=True, source_type="SHOPPING_LIST", source_hash=report.source_hash, comment=f"packs={item.packs_needed}"))
    db.commit()
    return len(report.items)


def apply_shopping_list_to_invoice_material_lines(db: Session, project_id: int, report: ShoppingListReport) -> int:
    invoice = db.query(Invoice).filter(Invoice.project_id == project_id, Invoice.status == "draft").order_by(Invoice.id.desc()).first()
    if invoice is None:
        raise ValueError("Draft invoice not found")
    by_material = {line.source_id: line for line in invoice.lines if line.source_type == "SHOPPING_LIST" and line.kind == "MATERIAL"}
    max_pos = max((line.position for line in invoice.lines), default=0)
    changed = 0
    for item in report.items:
        line = by_material.get(item.material_id)
        qty = Decimal(str(item.packs_needed))
        if line is None:
            max_pos += 1
            line = InvoiceLine(invoice_id=invoice.id, position=max_pos, kind="MATERIAL", source_type="SHOPPING_LIST", source_id=item.material_id)
            db.add(line)
        line.description = f"Shopping: {item.material_name}"
        line.unit = "pack"
        line.quantity = qty
        line.unit_price_ex_vat = _qm(item.unit_price or Decimal("0"))
        line.vat_rate_pct = _qm(Decimal("25"))
        line.source_hash = report.source_hash
        changed += 1
    db.flush()
    recalculate_invoice_totals(db, invoice.id)
    db.commit()
    return changed
