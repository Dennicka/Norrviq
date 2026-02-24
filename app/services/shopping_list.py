import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.cost import CostCategory, ProjectCostItem
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.project_procurement_settings import ProjectProcurementSettings
from app.models.supplier_material_price import SupplierMaterialPrice
from app.services.invoice_lines import recalculate_invoice_totals
from app.services.material_costing import cost_project_materials
from app.services.materials_bom import compute_project_bom

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


def _select_price(prices: list[SupplierMaterialPrice], preferred_supplier_id: int | None, auto_select_cheapest: bool) -> SupplierMaterialPrice | None:
    if not prices:
        return None
    if preferred_supplier_id:
        for price in prices:
            if price.supplier_id == preferred_supplier_id:
                return price
    if auto_select_cheapest:
        return min(prices, key=lambda p: (Decimal(str(p.pack_price_ex_vat or 0)), p.id))
    return min(prices, key=lambda p: (Decimal(str(p.pack_price_ex_vat or 0)), p.id))


def compute_project_shopping_list(db: Session, project_id: int) -> ShoppingListReport:
    bom = compute_project_bom(db, project_id)
    catalog_report = cost_project_materials(db, project_id)
    if not bom.items:
        items = [
            ShoppingListItem(
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
            )
            for idx, row in enumerate(catalog_report.rows, start=1)
        ]
        warning_codes = [f"material:{i.material_id}:{i.notes}" for i in items if i.notes]
        payload = {
            "project_id": project_id,
            "items": [{**asdict(item), "qty_final_unit": str(item.qty_final_unit)} for item in items],
            "totals": {"ex": str(catalog_report.total_ex_vat), "inc": str(catalog_report.total_inc_vat)},
        }
        source_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        return ShoppingListReport(
            project_id=project_id,
            source_hash=source_hash,
            items=items,
            total_ex_vat=catalog_report.total_ex_vat,
            total_inc_vat=catalog_report.total_inc_vat,
            warnings=warning_codes,
        )

    settings = get_or_create_procurement_settings(db, project_id)
    warnings: list[str] = []
    items: list[ShoppingListItem] = []

    for bom_item in bom.items:
        prices = db.query(SupplierMaterialPrice).filter(SupplierMaterialPrice.material_id == bom_item.material_id).all()
        price = _select_price(prices, settings.preferred_supplier_id, settings.auto_select_cheapest)
        vat_rate = Decimal("25.00")

        if price is None:
            unit_price = Decimal(str((bom_item.cost_ex_vat / bom_item.qty_final_unit) if bom_item.qty_final_unit > 0 else 0))
            total_ex = _qm(unit_price * bom_item.qty_final_unit)
            warnings.append(f"material:{bom_item.material_id}:NO_SUPPLIER_PRICE")
            items.append(
                ShoppingListItem(
                    material_id=bom_item.material_id,
                    material_name=bom_item.name,
                    sku=None,
                    unit=bom_item.unit,
                    qty_final_unit=bom_item.qty_final_unit,
                    supplier_name=None,
                    pack_size=None,
                    packs_count=0,
                    pack_price_ex_vat=unit_price,
                    total_ex_vat=total_ex,
                    vat_rate_pct=vat_rate,
                    estimated_cost_inc_vat=_qm(total_ex * (Decimal("1") + vat_rate / Decimal("100"))),
                    notes="fallback_default_cost_per_unit",
                )
            )
            continue

        pack_size = Decimal(str(price.pack_size or 0))
        if pack_size <= 0:
            warnings.append(f"material:{bom_item.material_id}:MISSING_PACK_SIZE")
            pack_size = bom_item.qty_final_unit if bom_item.qty_final_unit > 0 else Decimal("1")

        packs_count = 1
        if settings.rounding_mode.value == "CEIL_TO_PACKS":
            packs_count = int((bom_item.qty_final_unit / pack_size).to_integral_value(rounding=ROUND_CEILING)) if pack_size > 0 else 1

        pack_price = Decimal(str(price.pack_price_ex_vat or 0))
        total_ex = _qm(Decimal(packs_count) * pack_price)
        material = price.material
        vat_rate = Decimal(str(material.vat_rate_pct or 25))
        items.append(
            ShoppingListItem(
                material_id=bom_item.material_id,
                material_name=bom_item.name,
                sku=material.sku,
                unit=bom_item.unit,
                qty_final_unit=bom_item.qty_final_unit,
                supplier_name=price.supplier.name,
                pack_size=pack_size,
                packs_count=packs_count,
                pack_price_ex_vat=pack_price,
                total_ex_vat=total_ex,
                vat_rate_pct=vat_rate,
                estimated_cost_inc_vat=_qm(total_ex * (Decimal("1") + vat_rate / Decimal("100"))),
                notes=None,
            )
        )

    for unresolved in catalog_report.unresolved_rows:
        warnings.append(f"material:{unresolved.material_code}:UNRESOLVED_PRICING")

    total_ex = _qm(sum((i.total_ex_vat for i in items), start=Decimal("0")))
    total_inc = _qm(sum((i.estimated_cost_inc_vat for i in items), start=Decimal("0")))
    payload = {
        "project_id": project_id,
        "items": [
            {
                **asdict(item),
                "qty_final_unit": str(item.qty_final_unit),
                "pack_size": str(item.pack_size) if item.pack_size is not None else None,
                "pack_price_ex_vat": str(item.pack_price_ex_vat),
                "total_ex_vat": str(item.total_ex_vat),
            }
            for item in items
        ],
        "totals": {"ex": str(total_ex), "inc": str(total_inc)},
    }
    source_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return ShoppingListReport(project_id=project_id, source_hash=source_hash, items=items, total_ex_vat=total_ex, total_inc_vat=total_inc, warnings=sorted(set(warnings)))


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
        db.add(
            ProjectCostItem(
                project_id=project_id,
                cost_category_id=category.id,
                material_id=item.material_id,
                title=f"Shopping: {item.material_name}",
                amount=item.total_ex_vat,
                is_material=True,
                source_type="SHOPPING_LIST",
                source_hash=report.source_hash,
                comment=f"packs={item.packs_count}",
            )
        )
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
        qty = Decimal(item.packs_count)
        if line is None:
            max_pos += 1
            line = InvoiceLine(invoice_id=invoice.id, position=max_pos, kind="MATERIAL", source_type="SHOPPING_LIST", source_id=item.material_id)
            db.add(line)
        line.description = f"Shopping: {item.material_name}"
        line.unit = "pack"
        line.quantity = qty
        line.unit_price_ex_vat = _qm(item.pack_price_ex_vat)
        line.vat_rate_pct = _qm(item.vat_rate_pct)
        line.source_hash = report.source_hash
        changed += 1
    db.flush()
    recalculate_invoice_totals(db, invoice.id)
    db.commit()
    return changed
