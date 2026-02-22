from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.project_procurement_settings import ProjectProcurementSettings
from app.services.invoice_lines import recalculate_invoice_totals
from app.services.materials_bom import compute_project_bom
from app.services.shopping_list import compute_project_shopping_list

MONEY_Q = Decimal("0.01")
PRICING_SELL = "SELL_PRICE"
PRICING_COST_PLUS = "COST_PLUS_MARKUP"
UNIT_PACKS = "PACKS"
UNIT_BASE = "BASE_UNIT"
MERGE_REPLACE = "REPLACE_MATERIALS"
MERGE_APPEND = "APPEND"
MERGE_UPSERT = "UPSERT_BY_MATERIAL_ID"
SOURCE_SHOPPING = "SHOPPING_LIST"
SOURCE_BOM = "BOM"


def _q(v: Decimal) -> Decimal:
    return v.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _settings(db: Session, project_id: int) -> ProjectProcurementSettings:
    settings = db.query(ProjectProcurementSettings).filter_by(project_id=project_id).first()
    if settings:
        return settings
    settings = ProjectProcurementSettings(project_id=project_id)
    db.add(settings)
    db.flush()
    return settings


@dataclass
class MaterialLineDraft:
    material_id: int
    description: str
    qty: Decimal
    unit: str
    unit_price_ex_vat: Decimal
    vat_rate_pct: Decimal
    source_type: str
    source_hash: str | None = None


def _cost_plus(cost_per_unit: Decimal, markup_pct: Decimal) -> Decimal:
    return _q(cost_per_unit * (Decimal("1") + (markup_pct / Decimal("100"))))


def _from_shopping(db: Session, project_id: int, pricing_mode: str, markup_pct: Decimal, invoice_material_unit: str) -> tuple[list[MaterialLineDraft], str]:
    report = compute_project_shopping_list(db, project_id)
    lines: list[MaterialLineDraft] = []
    for item in report.items:
        pack_size = Decimal(str(item.pack_size or 0))
        if pack_size <= 0:
            pack_size = Decimal("1")
        sell_pack_price = _q(Decimal(str(item.pack_price_ex_vat)))
        if pricing_mode == PRICING_COST_PLUS:
            sell_pack_price = _cost_plus(sell_pack_price, markup_pct)
        if invoice_material_unit == UNIT_PACKS:
            qty = Decimal(str(item.packs_count or 0))
            if qty <= 0:
                qty = Decimal("1")
            unit = "pack"
            unit_price = sell_pack_price
            desc = f"{item.material_name} ({pack_size}{item.unit})"
        else:
            qty = _q(Decimal(str(item.qty_final_unit or 0)))
            unit = item.unit
            if pricing_mode == PRICING_SELL:
                unit_price = _q(sell_pack_price / pack_size)
            else:
                unit_price = _cost_plus(_q(Decimal(str(item.pack_price_ex_vat)) / pack_size), markup_pct)
            desc = item.material_name
        if item.sku:
            desc = f"{desc} [{item.sku}]"
        lines.append(MaterialLineDraft(item.material_id, desc, qty, unit, unit_price, _q(item.vat_rate_pct), SOURCE_SHOPPING, report.source_hash))
    return lines, report.source_hash


def _from_bom(db: Session, project_id: int, pricing_mode: str, markup_pct: Decimal, invoice_material_unit: str, round_to_packs: bool) -> tuple[list[MaterialLineDraft], str | None]:
    report = compute_project_bom(db, project_id)
    lines: list[MaterialLineDraft] = []
    for item in report.items:
        pack_size = Decimal(str(item.pack_size or item.qty_final_unit or 1))
        cost_per_unit = _q((Decimal(str(item.cost_ex_vat)) / Decimal(str(item.qty_final_unit))) if Decimal(str(item.qty_final_unit or 0)) > 0 else Decimal("0"))
        sell_per_unit = _q((Decimal(str(item.sell_ex_vat)) / Decimal(str(item.qty_final_unit))) if Decimal(str(item.qty_final_unit or 0)) > 0 else cost_per_unit)
        if pricing_mode == PRICING_COST_PLUS:
            sell_per_unit = _cost_plus(cost_per_unit, markup_pct)
        if invoice_material_unit == UNIT_PACKS:
            packs = Decimal(str(item.qty_final_unit or 0)) / pack_size
            packs_count = packs.to_integral_value(rounding=ROUND_CEILING) if round_to_packs else packs
            qty = _q(Decimal(str(packs_count)))
            unit = "pack"
            unit_price = _q(sell_per_unit * pack_size)
            desc = f"{item.name} ({pack_size}{item.unit})"
        else:
            qty = _q(Decimal(str(item.qty_final_unit or 0)))
            unit = item.unit
            unit_price = sell_per_unit
            desc = item.name
        lines.append(MaterialLineDraft(item.material_id, desc, qty, unit, unit_price, Decimal("25.00"), SOURCE_BOM))
    return lines, None


def add_material_lines(
    db: Session,
    *,
    project_id: int,
    invoice_id: int,
    source: str,
    merge_strategy: str,
    pricing_mode_override: str | None,
    user_id: str | None,
) -> int:
    invoice = db.get(Invoice, invoice_id)
    if not invoice or invoice.project_id != project_id:
        raise ValueError("Invoice not found")
    settings = _settings(db, project_id)
    pricing_mode = (pricing_mode_override or settings.material_pricing_mode or PRICING_COST_PLUS).upper()
    markup_pct = Decimal(str(settings.material_markup_pct or 20))
    invoice_unit = (settings.invoice_material_unit or UNIT_PACKS).upper()

    if source == SOURCE_SHOPPING:
        generated, source_hash = _from_shopping(db, project_id, pricing_mode, markup_pct, invoice_unit)
    else:
        generated, source_hash = _from_bom(db, project_id, pricing_mode, markup_pct, invoice_unit, bool(settings.round_invoice_materials_to_packs))

    existing = sorted(invoice.lines, key=lambda x: x.position)
    material_existing = [ln for ln in existing if ln.kind == "MATERIAL"]
    if merge_strategy == MERGE_REPLACE:
        for ln in material_existing:
            db.delete(ln)
        db.flush()
        existing = db.query(InvoiceLine).filter(InvoiceLine.invoice_id == invoice.id).order_by(InvoiceLine.position.asc()).all()
    by_material = {ln.source_id: ln for ln in existing if ln.kind == "MATERIAL"} if merge_strategy == MERGE_UPSERT else {}

    for payload in generated:
        line = by_material.get(payload.material_id)
        if line is None:
            line = InvoiceLine(invoice_id=invoice.id, kind="MATERIAL", source_type=payload.source_type, source_id=payload.material_id)
            existing.append(line)
            db.add(line)
        line.description = payload.description
        line.quantity = payload.qty
        line.unit = payload.unit
        line.unit_price_ex_vat = payload.unit_price_ex_vat
        line.vat_rate_pct = payload.vat_rate_pct
        line.source_hash = payload.source_hash

    for pos, line in enumerate(existing, start=1):
        line.position = pos
        db.add(line)

    recalculate_invoice_totals(db, invoice.id, user_id=user_id)
    db.add(AuditEvent(event_type="invoice_material_lines_added", user_id=user_id, entity_type="invoice", entity_id=invoice.id, details=f"source={source};count={len(generated)};merge={merge_strategy}"))
    invoice.material_pricing_snapshot = f"mode={pricing_mode};markup_pct={markup_pct};unit={invoice_unit};source={source}"
    invoice.material_source_snapshot_hash = source_hash
    db.add(invoice)
    db.flush()
    return len(generated)
