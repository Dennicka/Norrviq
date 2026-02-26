import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent
from app.models.material_actual_entry import ProjectMaterialActualEntry
from app.models.material_actuals import MaterialPurchase, MaterialPurchaseLine, ProjectMaterialActuals, ProjectMaterialStock
from app.models.project import Project
from app.models.supplier import Supplier
from app.services.materials_bom import compute_project_bom
from app.services.pdf_export import render_pdf_from_html
from app.services.shopping_list import compute_project_shopping_list

MONEY_Q = Decimal("0.01")


@dataclass
class PlanVsActualRow:
    material_id: int
    material_name: str
    planned_qty_unit: Decimal
    planned_packs: Decimal
    actual_qty_unit: Decimal
    actual_packs: Decimal
    delta_qty: Decimal
    delta_packs: Decimal
    planned_cost_ex_vat: Decimal
    actual_cost_ex_vat: Decimal
    delta_cost: Decimal
    status: str


@dataclass
class PlanVsActualReport:
    rows: list[PlanVsActualRow]
    planned_cost_ex_vat: Decimal
    actual_cost_ex_vat: Decimal
    delta_cost_ex_vat: Decimal
    warnings: list[str]


def _qm(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _audit(db: Session, *, event_type: str, project_id: int, user_id: int | None, details: dict | None = None) -> None:
    db.add(AuditEvent(event_type=event_type, user_id=str(user_id) if user_id else None, entity_type="PROJECT", entity_id=project_id, details=json.dumps(details or {}, ensure_ascii=False)))


def upsert_actual_entry(db: Session, *, project_id: int, material_name: str, actual_qty: Decimal, actual_packages: Decimal, actual_cost_sek: Decimal, supplier: str | None, receipt_note: str | None) -> ProjectMaterialActualEntry:
    row = (
        db.query(ProjectMaterialActualEntry)
        .filter(ProjectMaterialActualEntry.project_id == project_id, func.lower(ProjectMaterialActualEntry.material_name) == material_name.lower())
        .first()
    )
    if not row:
        row = ProjectMaterialActualEntry(project_id=project_id, material_name=material_name)
        db.add(row)
    row.actual_qty = actual_qty
    row.actual_packages = actual_packages
    row.actual_cost_sek = actual_cost_sek
    row.supplier = supplier
    row.receipt_note = receipt_note
    db.flush()
    return row


def create_material_purchase(db: Session, *, project_id: int, supplier_id: int | None, purchased_at: datetime, invoice_ref: str | None, notes: str | None, currency: str, user_id: int | None, lines: list[dict], idempotency_key: str | None = None) -> MaterialPurchase:
    if not db.get(Project, project_id):
        raise ValueError("Project not found")
    if supplier_id and not db.get(Supplier, supplier_id):
        raise ValueError("Supplier not found")
    if idempotency_key:
        existing = db.query(MaterialPurchase).filter_by(project_id=project_id, idempotency_key=idempotency_key).first()
        if existing:
            return existing

    purchase = MaterialPurchase(project_id=project_id, supplier_id=supplier_id, purchased_at=purchased_at, invoice_ref=invoice_ref, notes=notes, currency=currency or "SEK", created_by_user_id=user_id, idempotency_key=idempotency_key)
    db.add(purchase)
    db.flush()

    for line in lines:
        packs_count = Decimal(str(line["packs_count"]))
        pack_size = Decimal(str(line["pack_size"]))
        pack_price = Decimal(str(line["pack_price_ex_vat"]))
        vat_rate = Decimal(str(line.get("vat_rate_pct") or "25.00"))
        if packs_count <= 0 or pack_size <= 0 or pack_price < 0:
            raise ValueError("Invalid purchase line")
        cost_ex = _qm(packs_count * pack_price)
        cost_inc = _qm(cost_ex * (Decimal("1") + vat_rate / Decimal("100")))
        db_line = MaterialPurchaseLine(purchase_id=purchase.id, material_id=int(line["material_id"]), packs_count=packs_count, pack_size=pack_size, unit=line["unit"], pack_price_ex_vat=pack_price, vat_rate_pct=vat_rate, line_cost_ex_vat=cost_ex, line_cost_inc_vat=cost_inc, source=line.get("source") or "MANUAL")
        db.add(db_line)
        stock = db.query(ProjectMaterialStock).filter_by(project_id=project_id, material_id=int(line["material_id"])).first()
        if not stock:
            stock = ProjectMaterialStock(project_id=project_id, material_id=int(line["material_id"]), qty_in_base_unit=Decimal("0"))
            db.add(stock)
        stock.qty_in_base_unit = _qm(Decimal(str(stock.qty_in_base_unit or 0)) + (packs_count * pack_size))
        _audit(db, event_type="material_purchase_line_added", project_id=project_id, user_id=user_id, details={"purchase_id": purchase.id, "material_id": int(line["material_id"])})

    _recalculate_project_actuals(db, project_id)
    _audit(db, event_type="material_purchase_created", project_id=project_id, user_id=user_id, details={"purchase_id": purchase.id, "lines_count": len(lines)})
    db.commit()
    db.refresh(purchase)
    return purchase


def _recalculate_project_actuals(db: Session, project_id: int) -> ProjectMaterialActuals:
    row = db.query(func.coalesce(func.sum(MaterialPurchaseLine.line_cost_ex_vat), 0), func.coalesce(func.sum(MaterialPurchaseLine.line_cost_inc_vat), 0)).join(MaterialPurchase, MaterialPurchase.id == MaterialPurchaseLine.purchase_id).filter(MaterialPurchase.project_id == project_id).one()
    ex = _qm(Decimal(str(row[0] or 0)))
    inc = _qm(Decimal(str(row[1] or 0)))
    actuals = db.query(ProjectMaterialActuals).filter_by(project_id=project_id).first()
    if not actuals:
        actuals = ProjectMaterialActuals(project_id=project_id)
        db.add(actuals)
    actuals.actual_cost_ex_vat = ex
    actuals.actual_cost_inc_vat = inc
    _audit(db, event_type="material_actuals_updated", project_id=project_id, user_id=None, details={"actual_cost_ex_vat": str(ex)})
    db.flush()
    return actuals


def compute_materials_plan_vs_actual(db: Session, project_id: int) -> PlanVsActualReport:
    bom = compute_project_bom(db, project_id)
    shopping = compute_project_shopping_list(db, project_id)
    purchases = db.query(MaterialPurchaseLine, MaterialPurchase).join(MaterialPurchase, MaterialPurchase.id == MaterialPurchaseLine.purchase_id).filter(MaterialPurchase.project_id == project_id).all()
    actual_entries = db.query(ProjectMaterialActualEntry).filter(ProjectMaterialActualEntry.project_id == project_id).all()

    by_material: dict[str, dict] = {}
    warnings: list[str] = []
    for item in bom.items:
        key = item.name.lower()
        by_material[key] = {"material_id": item.material_id, "name": item.name, "planned_qty": Decimal(str(item.qty_final_unit)), "planned_packs": Decimal(str(item.packs_count or 0)), "planned_cost": Decimal(str(item.cost_ex_vat)), "actual_qty": Decimal("0"), "actual_packs": Decimal("0"), "actual_cost": Decimal("0")}
    for s in shopping.items:
        for key, value in by_material.items():
            if value["material_id"] == s.material_id:
                value["planned_packs"] = Decimal(str(s.packs_count))
                if s.unit_price is not None and "NO_SUPPLIER_PRICE" not in s.warnings:
                    value["planned_cost"] = Decimal(str(s.total_ex_vat))

    for line, _purchase in purchases:
        key = (line.material.name_sv if line.material else f"material_{line.material_id}").lower()
        bucket = by_material.setdefault(key, {"material_id": line.material_id, "name": line.material.name_sv if line.material else f"Material #{line.material_id}", "planned_qty": Decimal("0"), "planned_packs": Decimal("0"), "planned_cost": Decimal("0"), "actual_qty": Decimal("0"), "actual_packs": Decimal("0"), "actual_cost": Decimal("0")})
        bucket["actual_qty"] += Decimal(str(line.packs_count)) * Decimal(str(line.pack_size))
        bucket["actual_packs"] += Decimal(str(line.packs_count))
        bucket["actual_cost"] += Decimal(str(line.line_cost_ex_vat))

    for entry in actual_entries:
        key = entry.material_name.lower()
        bucket = by_material.setdefault(key, {"material_id": 0, "name": entry.material_name, "planned_qty": Decimal("0"), "planned_packs": Decimal("0"), "planned_cost": Decimal("0"), "actual_qty": Decimal("0"), "actual_packs": Decimal("0"), "actual_cost": Decimal("0")})
        bucket["actual_qty"] += Decimal(str(entry.actual_qty or 0))
        bucket["actual_packs"] += Decimal(str(entry.actual_packages or 0))
        bucket["actual_cost"] += Decimal(str(entry.actual_cost_sek or 0))

    rows: list[PlanVsActualRow] = []
    for _, data in by_material.items():
        delta_qty = _qm(data["actual_qty"] - data["planned_qty"])
        delta_packs = _qm(data["actual_packs"] - data["planned_packs"])
        delta_cost = _qm(data["actual_cost"] - data["planned_cost"])
        status = "OK" if delta_qty == 0 else ("OVER" if delta_qty > 0 else "UNDER")
        rows.append(PlanVsActualRow(material_id=int(data["material_id"]), material_name=data["name"], planned_qty_unit=_qm(data["planned_qty"]), planned_packs=_qm(data["planned_packs"]), actual_qty_unit=_qm(data["actual_qty"]), actual_packs=_qm(data["actual_packs"]), delta_qty=delta_qty, delta_packs=delta_packs, planned_cost_ex_vat=_qm(data["planned_cost"]), actual_cost_ex_vat=_qm(data["actual_cost"]), delta_cost=delta_cost, status=status))

    planned = _qm(sum((r.planned_cost_ex_vat for r in rows), start=Decimal("0")))
    actual = _qm(sum((r.actual_cost_ex_vat for r in rows), start=Decimal("0")))
    return PlanVsActualReport(rows=sorted(rows, key=lambda r: r.material_name.lower()), planned_cost_ex_vat=planned, actual_cost_ex_vat=actual, delta_cost_ex_vat=_qm(actual - planned), warnings=sorted(set(warnings)))


def export_plan_vs_actual_csv(report: PlanVsActualReport) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["material_id", "material_name", "planned_qty_unit", "actual_qty_unit", "delta_qty", "planned_cost_ex_vat", "actual_cost_ex_vat", "delta_cost", "status"])
    for row in report.rows:
        w.writerow([row.material_id, row.material_name, str(row.planned_qty_unit), str(row.actual_qty_unit), str(row.delta_qty), str(row.planned_cost_ex_vat), str(row.actual_cost_ex_vat), str(row.delta_cost), row.status])
    return out.getvalue()


def export_purchases_csv(db: Session, project_id: int) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["purchase_id", "purchased_at", "material_id", "material_name", "packs_count", "pack_size", "pack_price_ex_vat", "line_cost_ex_vat", "source"])
    rows = db.query(MaterialPurchaseLine, MaterialPurchase).join(MaterialPurchase, MaterialPurchase.id == MaterialPurchaseLine.purchase_id).filter(MaterialPurchase.project_id == project_id).all()
    for line, purchase in rows:
        w.writerow([purchase.id, purchase.purchased_at.isoformat() if purchase.purchased_at else "", line.material_id, line.material.name_sv if line.material else "", str(line.packs_count), str(line.pack_size), str(line.pack_price_ex_vat), str(line.line_cost_ex_vat), line.source])
    return out.getvalue()


def build_quick_add_idempotency_key(project_id: int, payload: dict) -> str:
    return hashlib.sha256(json.dumps({"project_id": project_id, **payload}, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def export_plan_vs_actual_pdf(*, html: str, base_url, stylesheet_path) -> bytes:
    return render_pdf_from_html(html=html, base_url=base_url, stylesheet_path=stylesheet_path)
