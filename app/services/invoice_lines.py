from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session, selectinload

from app.models.audit_event import AuditEvent
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.cost import ProjectCostItem
from app.models.project import Project, ProjectWorkItem

DEFAULT_VAT_RATE = Decimal("25.00")

MERGE_REPLACE_ALL = "REPLACE_ALL"
MERGE_APPEND = "APPEND"
MERGE_UPSERT_BY_SOURCE = "UPSERT_BY_SOURCE"


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def recalculate_invoice_totals(db: Session, invoice_id: int, user_id: str | None = None) -> Invoice:
    db.flush()
    invoice = db.query(Invoice).options(selectinload(Invoice.lines)).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise ValueError("Invoice not found")

    subtotal = Decimal("0.00")
    vat_total = Decimal("0.00")

    for line in sorted(invoice.lines, key=lambda ln: ln.position):
        qty = _q(Decimal(str(line.quantity or 0)))
        price = _q(Decimal(str(line.unit_price_ex_vat or 0)))
        vat_rate = _q(Decimal(str(line.vat_rate_pct if line.vat_rate_pct is not None else DEFAULT_VAT_RATE)))

        line.quantity = qty
        line.unit_price_ex_vat = price
        line.vat_rate_pct = vat_rate

        line.line_total_ex_vat = _q(qty * price)
        line.vat_amount = _q(line.line_total_ex_vat * vat_rate / Decimal("100"))
        line.line_total_inc_vat = _q(line.line_total_ex_vat + line.vat_amount)

        subtotal += line.line_total_ex_vat
        vat_total += line.vat_amount

    invoice.subtotal_ex_vat = _q(subtotal)
    invoice.vat_total = _q(vat_total)
    invoice.total_inc_vat = _q(invoice.subtotal_ex_vat + invoice.vat_total)

    invoice.work_sum_without_moms = invoice.subtotal_ex_vat
    invoice.moms_amount = invoice.vat_total
    invoice.rot_amount = Decimal("0.00")
    invoice.client_pays_total = invoice.total_inc_vat

    db.add(
        AuditEvent(
            event_type="invoice_totals_recalculated",
            user_id=user_id,
            entity_type="invoice",
            entity_id=invoice.id,
            details=f"lines={len(invoice.lines)} subtotal={invoice.subtotal_ex_vat}",
        )
    )
    db.flush()
    return invoice


def _labor_description(item: ProjectWorkItem) -> str:
    room = item.room.name if item.room else "No room"
    wt = item.work_type.name_sv if item.work_type else "Work"
    note = (item.comment or "").strip()
    return f"{wt} — {room}" + (f" ({note})" if note else "")


def _generate_labor_lines(project: Project) -> list[dict]:
    mode = (project.pricing.mode if project.pricing else "HOURLY").upper()
    items = sorted(project.work_items, key=lambda wi: wi.id)

    if mode in {"FIXED_TOTAL", "PER_M2", "PER_ROOM"}:
        total = Decimal(str(project.pricing.fixed_total_price or 0)) if project.pricing else Decimal("0")
        return [{
            "kind": "LABOR",
            "description": "Fixed price (labour)",
            "unit": "st",
            "quantity": Decimal("1.00"),
            "unit_price_ex_vat": _q(total),
            "vat_rate_pct": DEFAULT_VAT_RATE,
            "source_type": "MANUAL",
            "source_id": None,
        }]

    hourly_rate = Decimal(str(project.pricing.hourly_rate_override if project.pricing and project.pricing.hourly_rate_override is not None else 0))
    lines = []
    for item in items:
        qty = Decimal(str(item.calculated_hours if item.calculated_hours is not None else item.quantity or 0))
        unit = "h" if item.calculated_hours is not None else (item.work_type.unit if item.work_type else None)
        price = hourly_rate if unit == "h" else Decimal(str(item.calculated_cost_without_moms or 0)) / (qty or Decimal("1"))
        lines.append(
            {
                "kind": "LABOR",
                "description": _labor_description(item),
                "unit": unit,
                "quantity": _q(qty),
                "unit_price_ex_vat": _q(price),
                "vat_rate_pct": DEFAULT_VAT_RATE,
                "source_type": "WORK_ITEM",
                "source_id": item.id,
            }
        )
    return lines


def _generate_material_lines(project: Project) -> list[dict]:
    lines: list[dict] = []
    for item in sorted(project.cost_items, key=lambda ci: ci.id):
        if not item.is_material:
            continue
        amount = _q(Decimal(str(item.amount or 0)))
        if amount <= 0:
            continue
        category_name = item.category.name_sv if item.category else "Material"
        lines.append(
            {
                "kind": "MATERIAL",
                "description": item.title or category_name,
                "unit": "st",
                "quantity": Decimal("1.00"),
                "unit_price_ex_vat": amount,
                "vat_rate_pct": DEFAULT_VAT_RATE,
                "source_type": "COST_ITEM",
                "source_id": item.id,
            }
        )
    return lines


def generate_invoice_lines_from_project(
    db: Session,
    *,
    project_id: int,
    invoice_id: int,
    include_labor: bool = True,
    include_materials: bool = False,
    merge_strategy: str = MERGE_REPLACE_ALL,
    user_id: str | None = None,
) -> Invoice:
    invoice = db.query(Invoice).options(selectinload(Invoice.lines)).filter(Invoice.id == invoice_id, Invoice.project_id == project_id).first()
    if not invoice:
        raise ValueError("Invoice not found")
    project = db.query(Project).options(
        selectinload(Project.pricing),
        selectinload(Project.work_items).selectinload(ProjectWorkItem.room),
        selectinload(Project.work_items).selectinload(ProjectWorkItem.work_type),
        selectinload(Project.cost_items).selectinload(ProjectCostItem.category),
        selectinload(Project.cost_items).selectinload(ProjectCostItem.material),
    ).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Project not found")

    generated: list[dict] = []
    if include_labor:
        generated.extend(_generate_labor_lines(project))
    if include_materials:
        generated.extend(_generate_material_lines(project))

    existing = sorted(invoice.lines, key=lambda ln: ln.position)

    if merge_strategy == MERGE_REPLACE_ALL:
        for line in existing:
            db.delete(line)
        db.flush()
        base = []
    elif merge_strategy == MERGE_APPEND:
        base = existing
    elif merge_strategy == MERGE_UPSERT_BY_SOURCE:
        base = existing
    else:
        raise ValueError("Unsupported merge strategy")

    if merge_strategy == MERGE_UPSERT_BY_SOURCE:
        by_source = {(line.source_type, line.source_id): line for line in base if line.source_type and line.source_id is not None}
        for payload in generated:
            key = (payload["source_type"], payload["source_id"])
            if key in by_source:
                line = by_source[key]
                for field in ("kind", "description", "unit", "quantity", "unit_price_ex_vat", "vat_rate_pct"):
                    setattr(line, field, payload[field])
            else:
                base.append(InvoiceLine(invoice_id=invoice.id, **payload))
    else:
        for payload in generated:
            base.append(InvoiceLine(invoice_id=invoice.id, **payload))

    for idx, line in enumerate(base, start=1):
        line.position = idx
        db.add(line)

    recalculate_invoice_totals(db, invoice.id, user_id=user_id)
    db.add(
        AuditEvent(
            event_type="invoice_lines_generated",
            user_id=user_id,
            entity_type="invoice",
            entity_id=invoice.id,
            details=f"strategy={merge_strategy} lines={len(generated)} include_materials={include_materials}",
        )
    )
    db.flush()
    return invoice
