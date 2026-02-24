from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.invoice import Invoice
from app.models.project import Project
from app.services.invoice_commercial import compute_invoice_commercial
from app.services.offer_commercial import compute_offer_commercial
from app.services.pricing import compute_pricing_scenarios
from app.services.pricing_consistency import validate_pricing_consistency
from app.services.project_pricing import build_project_pricing_summary
from app.services.rounding import money_eq, round_money_sek, to_decimal


@dataclass
class CorrectnessLockResult:
    ok: bool
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)


def _err(code: str, message: str, **meta: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "meta": meta}


def _is_invalid_number(value: object) -> bool:
    if value is None:
        return True
    try:
        number = float(value)
    except (TypeError, ValueError):
        return True
    return math.isnan(number) or math.isinf(number)


def validate_estimate_invariants(project: Project) -> CorrectnessLockResult:
    errors: list[dict[str, Any]] = []
    totals = {
        "total_hours": sum((to_decimal(getattr(i, "calculated_hours", 0)) for i in getattr(project, "work_items", [])), Decimal("0")),
        "labour_cost": project.work_sum_without_moms,
        "materials_cost": project.materials_cost,
        "total_cost": project.total_cost,
    }
    for metric_name, raw in totals.items():
        if _is_invalid_number(raw):
            errors.append(_err("ESTIMATE_INVALID_NUMBER", f"{metric_name} has invalid value", field=metric_name, value=raw))
            continue
        if to_decimal(raw) < 0:
            errors.append(_err("ESTIMATE_NEGATIVE_TOTAL", f"{metric_name} cannot be negative", field=metric_name, value=str(raw)))

    for item in getattr(project, "work_items", []):
        quantity = to_decimal(item.quantity or 0)
        if quantity < 0:
            errors.append(_err("ESTIMATE_NEGATIVE_QUANTITY", "Work line quantity cannot be negative", work_item_id=item.id, quantity=str(quantity)))

    components_sum = round_money_sek(to_decimal(project.work_sum_without_moms or 0) + to_decimal(project.materials_cost or 0) + to_decimal(project.overhead_amount or 0))
    total_cost = round_money_sek(project.total_cost or 0)
    if getattr(project, "work_items", None) and not money_eq(total_cost, components_sum):
        errors.append(_err("ESTIMATE_TOTAL_MISMATCH", "Project total cost does not match labour + materials + overhead", total_cost=str(total_cost), components_sum=str(components_sum)))

    return CorrectnessLockResult(ok=not errors, errors=errors)


def validate_pricing_invariants(db: Session, project: Project) -> CorrectnessLockResult:
    errors: list[dict[str, Any]] = []
    baseline, scenarios = compute_pricing_scenarios(db, project.id)
    summary = build_project_pricing_summary(project, db)
    selected = next((s for s in scenarios if s.mode == (project.pricing.mode if project.pricing else "HOURLY")), None)
    if not selected:
        errors.append(_err("PRICING_MODE_NOT_FOUND", "Selected pricing mode does not have computed scenario"))
        return CorrectnessLockResult(ok=False, errors=errors)

    if not money_eq(selected.price_ex_vat, summary.selected_total_with_materials):
        errors.append(_err("PRICING_SELECTED_TOTAL_MISMATCH", "Selected pricing total differs from displayed selected total", selected=str(selected.price_ex_vat), displayed=str(summary.selected_total_with_materials)))

    baseline2, scenarios2 = compute_pricing_scenarios(db, project.id)
    if str(baseline) != str(baseline2) or [str(s) for s in scenarios] != [str(s) for s in scenarios2]:
        errors.append(_err("PRICING_NON_DETERMINISTIC", "Pricing comparison scenarios are not deterministic"))

    for scenario in scenarios:
        target = scenario.input_params.get("target_margin_pct") if scenario.input_params else None
        if target is not None and scenario.price_ex_vat:
            # coarse sanity: calculated margin should not drift heavily from input target
            if abs(to_decimal(target) - to_decimal(scenario.margin_pct or 0)) > Decimal("1.00"):
                errors.append(_err("PRICING_MARGIN_MISMATCH", "Margin % is not aligned with totals", mode=scenario.mode, target=str(target), actual=str(scenario.margin_pct)))

    if selected.mode == "FIXED_TOTAL":
        consistency = validate_pricing_consistency(db, project.id, "OFFER")
        if not consistency.ok:
            errors.append(_err("PRICING_FIXED_COMPLETENESS_GUARD", "Fixed pricing mode fails consistency/completeness checks", issues=consistency.errors))

    return CorrectnessLockResult(ok=not errors, errors=errors)


def validate_offer_invariants(db: Session, project: Project) -> CorrectnessLockResult:
    errors: list[dict[str, Any]] = []
    if project.offer_status == "issued" and not project.offer_number:
        errors.append(_err("OFFER_MISSING_NUMBER", "Issued offer must have a document number", project_id=project.id))
    commercial = compute_offer_commercial(db, project.id)
    if not money_eq(commercial.price_inc_vat, to_decimal(commercial.price_ex_vat) + to_decimal(commercial.vat_amount)):
        errors.append(_err("OFFER_TOTAL_MISMATCH", "Offer totals are inconsistent with VAT", project_id=project.id))
    return CorrectnessLockResult(ok=not errors, errors=errors)


def validate_invoice_invariants(db: Session, invoice: Invoice) -> CorrectnessLockResult:
    errors: list[dict[str, Any]] = []
    if invoice.status == "issued" and not invoice.invoice_number:
        errors.append(_err("INVOICE_MISSING_NUMBER", "Issued invoice must have document number", invoice_id=invoice.id))

    lines_sum = round_money_sek(sum((to_decimal(line.line_total_ex_vat) for line in invoice.lines), Decimal("0")))
    if not money_eq(lines_sum, invoice.subtotal_ex_vat or 0):
        errors.append(_err("INVOICE_LINES_SUM_MISMATCH", "Invoice subtotal must equal sum of line totals", invoice_id=invoice.id, lines_sum=str(lines_sum), subtotal=str(invoice.subtotal_ex_vat)))

    commercial = compute_invoice_commercial(db, invoice.project_id, invoice.id)
    if not money_eq(commercial.price_inc_vat, invoice.total_inc_vat or 0):
        errors.append(_err("INVOICE_COMMERCIAL_MISMATCH", "Invoice totals mismatch computed commercial totals", invoice_id=invoice.id))

    if invoice.source_project_id:
        draft_count = db.query(Invoice).filter(Invoice.source_project_id == invoice.source_project_id, Invoice.status == "draft").count()
        if draft_count > 1:
            errors.append(_err("INVOICE_DUPLICATE_DRAFT", "Duplicate draft invoices for project are not allowed", project_id=invoice.source_project_id, draft_count=draft_count))

    return CorrectnessLockResult(ok=not errors, errors=errors)
