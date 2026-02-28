import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.cost import CostCategory, ProjectCostItem
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.material import Material
from app.models.project_procurement_settings import ProjectProcurementSettings
from app.services.invoice_lines import recalculate_invoice_totals
from app.services.materials_bom import ProcurementStrategy, compute_procurement_plan
from app.services.procurement_rounding import ProcurementRoundingPolicy
from app.services.request_cache import RequestCache, cache_key

MONEY_Q = Decimal("0.01")


@dataclass
class ShoppingListItem:
    material_id: int
    material_name: str
    planned_qty: Decimal
    planned_unit: str
    pack_size: Decimal | None
    pack_unit: str | None
    packs_needed: Decimal | None
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
        return self.packs_needed or Decimal("0")

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


def compute_project_shopping_list(
    db: Session,
    project_id: int,
    supplier_id: int | None = None,
    group_by_supplier: bool = True,
    include_items_without_price: bool = True,
    strategy: str | None = None,
    policy: ProcurementRoundingPolicy | None = None,
    cache: RequestCache | None = None,
) -> ShoppingListReport:
    settings = get_or_create_procurement_settings(db, project_id)
    strategy_mode = (strategy or ("PREFERRED_FIRST" if settings.preferred_supplier_id else "CHEAPEST")).upper()
    cache_token = f"{supplier_id}:{group_by_supplier}:{include_items_without_price}:{strategy_mode}:{policy}"
    key = cache_key("shopping_list", project_id, cache_token)
    if cache is not None:
        cached = cache.get(key)
        if cached is not None:
            return cached
    if strategy_mode == "FIXED_SUPPLIER" and not supplier_id:
        supplier_id = settings.preferred_supplier_id
    plan = compute_procurement_plan(
        db,
        project_id,
        strategy=ProcurementStrategy(strategy_mode if strategy_mode in {"CHEAPEST", "PREFERRED_FIRST", "FIXED_SUPPLIER"} else "CHEAPEST"),
        supplier_id=supplier_id or settings.preferred_supplier_id,
        policy=policy,
        cache=cache,
    )
    warnings: list[str] = list(plan.warnings)
    items: list[ShoppingListItem] = []

    material_ids = [line.material_id for line in plan.lines]
    materials = db.query(Material).filter(Material.id.in_(material_ids)).all() if material_ids else []
    materials_by_id = {material.id: material for material in materials}

    for line in plan.lines:
        planned_qty = Decimal(str(line.qty or 0))
        if planned_qty <= 0:
            continue
        material = materials_by_id.get(line.material_id)
        pack_size = None
        pack_unit = line.unit
        if material and material.pack_size is not None:
            pack_size = Decimal(str(material.pack_size))
            pack_unit = material.pack_unit or line.unit

        if pack_size is None and line.packs_needed is not None and line.packs_needed > 0:
            pack_size = (line.purchase_qty / line.packs_needed) if line.packs_needed > 0 else None

        line_warnings = list(line.warnings)
        is_unpriced = line.packs_needed is None or line.unit_price_ex_vat is None
        if is_unpriced:
            line_warnings.append("UNPRICED_DUE_TO_UNIT_MISMATCH")
        if line.unit_price_ex_vat is None:
            if not include_items_without_price:
                continue
            line_warnings.append("NO_SUPPLIER_PRICE")

        items.append(
            ShoppingListItem(
                material_id=line.material_id,
                material_name=line.material_name,
                planned_qty=planned_qty,
                planned_unit=line.unit,
                pack_size=pack_size,
                pack_unit=pack_unit,
                packs_needed=line.packs_needed,
                purchase_qty=_qm(line.purchase_qty),
                supplier_id=line.supplier_id,
                supplier_name=line.supplier_name,
                unit_price=line.unit_price_ex_vat,
                line_total_cost=_qm(line.line_total_cost_ex_vat),
                warnings=sorted(set(line_warnings)),
            )
        )

    items = sorted(items, key=lambda i: (i.material_name.lower(), i.material_id))
    grouped: dict[str, list[ShoppingListItem]] = {}
    if group_by_supplier:
        for item in items:
            supplier_key = item.supplier_name or "Unassigned"
            grouped.setdefault(supplier_key, []).append(item)

    total_packs = _qm(sum(((item.packs_needed or Decimal("0")) for item in items), start=Decimal("0")))
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
    result = ShoppingListReport(project_id=project_id, source_hash=source_hash, items=items, total_packs=total_packs, total_cost_sek=total_cost, grouped_by_supplier=grouped, warnings=sorted(set(warnings)))
    if cache is not None:
        cache.set(key, result)
    return result


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
        qty = Decimal(str(item.packs_needed or 0))
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
