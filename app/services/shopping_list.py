from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.cost import CostCategory, ProjectCostItem
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.project_procurement_settings import ProjectProcurementSettings
from app.services.invoice_lines import recalculate_invoice_totals
from app.services.material_costing import cost_project_materials

MONEY_Q = Decimal("0.01")


@dataclass
class ShoppingListItem:
    material_id: int
    material_name: str
    sku: str | None
    unit: str
    qty_final_unit: Decimal
    supplier_name: str | None
    pack_size: Decimal | None
    packs_count: int
    pack_price_ex_vat: Decimal
    total_ex_vat: Decimal
    vat_rate_pct: Decimal
    estimated_cost_inc_vat: Decimal
    notes: str | None


@dataclass
class ShoppingListReport:
    project_id: int
    source_hash: str
    items: list[ShoppingListItem]
    total_ex_vat: Decimal
    total_inc_vat: Decimal
    warnings: list[str]


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


def compute_project_shopping_list(db: Session, project_id: int) -> ShoppingListReport:
    report = cost_project_materials(db, project_id)
    items: list[ShoppingListItem] = []
    warnings: list[str] = []
    for idx, row in enumerate(report.rows, start=1):
        if row.warnings:
            warnings.extend([f"{row.material_code}:{w}" for w in row.warnings])
        items.append(ShoppingListItem(
            material_id=idx,
            material_name=row.material_name,
            sku=None,
            unit=row.required_unit,
            qty_final_unit=row.required_quantity,
            supplier_name=None,
            pack_size=row.package_size,
            packs_count=row.packages_to_buy,
            pack_price_ex_vat=row.unit_price_ex_vat,
            total_ex_vat=row.total_ex_vat,
            vat_rate_pct=Decimal("25.00") if row.total_ex_vat == 0 else _qm(row.total_vat / row.total_ex_vat * Decimal("100")),
            estimated_cost_inc_vat=row.total_inc_vat,
            notes=", ".join(row.warnings) if row.warnings else None,
        ))
    source_hash = f"material-costing:{project_id}:{len(items)}:{report.total_ex_vat}"
    return ShoppingListReport(project_id=project_id, source_hash=source_hash, items=items, total_ex_vat=report.total_ex_vat, total_inc_vat=report.total_inc_vat, warnings=warnings)


def apply_shopping_list_to_project_cost_items(db: Session, project_id: int, report: ShoppingListReport) -> int:
    category = db.query(CostCategory).filter(CostCategory.code == "MATERIALS").first()
    if not category:
        category = CostCategory(code="MATERIALS", name_ru="Материалы", name_sv="Material")
        db.add(category)
        db.flush()
    for item in report.items:
        if item.total_ex_vat <= 0:
            continue
        db.add(ProjectCostItem(project_id=project_id, cost_category_id=category.id, title=f"Shopping: {item.material_name}", amount=item.total_ex_vat, is_material=True, source_type="SHOPPING_LIST", source_hash=report.source_hash, comment=f"packs={item.packs_count}"))
    db.commit()
    return len(report.items)


def apply_shopping_list_to_invoice_material_lines(db: Session, project_id: int, report: ShoppingListReport) -> int:
    invoice = db.query(Invoice).filter(Invoice.project_id == project_id, Invoice.status == "draft").order_by(Invoice.id.desc()).first()
    if invoice is None:
        raise ValueError("Draft invoice not found")
    max_pos = max((line.position for line in invoice.lines), default=0)
    changed = 0
    for item in report.items:
        if item.packs_count <= 0:
            continue
        max_pos += 1
        db.add(InvoiceLine(invoice_id=invoice.id, position=max_pos, kind="MATERIAL", source_type="SHOPPING_LIST", source_id=item.material_id, description=f"Shopping: {item.material_name}", unit="pack", quantity=Decimal(item.packs_count), unit_price_ex_vat=_qm(item.pack_price_ex_vat), vat_rate_pct=_qm(item.vat_rate_pct), source_hash=report.source_hash))
        changed += 1
    db.flush()
    recalculate_invoice_totals(db, invoice.id)
    db.commit()
    return changed
