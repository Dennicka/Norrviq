from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.invoice import Invoice
from app.models.project import Project
from app.services.invoice_commercial import compute_invoice_commercial
from app.services.offer_commercial import compute_offer_commercial
from app.services.pricing import compute_pricing_scenarios

TOLERANCE = Decimal("0.01")
DOC_TYPE_OFFER = "OFFER"
DOC_TYPE_INVOICE = "INVOICE"


@dataclass
class ConsistencyResult:
    ok: bool
    errors: list[dict]
    debug: dict = field(default_factory=dict)


def _eq(a, b) -> bool:
    return abs(Decimal(str(a or 0)) - Decimal(str(b or 0))) <= TOLERANCE


def validate_pricing_consistency(db: Session, project_id: int, doc_type: str, doc_id: int | None = None) -> ConsistencyResult:
    errors: list[dict] = []
    debug: dict = {}
    project = db.get(Project, project_id)
    if not project:
        return ConsistencyResult(ok=False, errors=[{"code": "PROJECT_NOT_FOUND", "message": "Project not found"}], debug={})

    mode = (project.pricing.mode if project.pricing else None)
    if not mode:
        errors.append({"code": "MISSING_SELECTED_MODE", "message": "Selected pricing mode is missing"})
        return ConsistencyResult(ok=False, errors=errors, debug=debug)

    baseline, scenarios = compute_pricing_scenarios(db, project_id)
    scenario = next((s for s in scenarios if s.mode == mode), None)
    if scenario is None:
        errors.append({"code": "SCENARIO_NOT_FOUND", "message": f"Pricing scenario for mode {mode} not found"})
        return ConsistencyResult(ok=False, errors=errors, debug=debug)

    commercial = compute_offer_commercial(db, project_id) if doc_type == DOC_TYPE_OFFER else compute_invoice_commercial(db, project_id, doc_id)
    debug["scenario_price_ex_vat"] = str(scenario.price_ex_vat)
    debug["commercial_price_ex_vat"] = str(commercial.price_ex_vat)

    if not _eq(scenario.price_ex_vat, commercial.price_ex_vat):
        errors.append({"code": "TOTAL_PRICE_EX_VAT_MISMATCH", "message": "Pricing scenario total differs from commercial total"})

    if mode == "PER_M2":
        if not baseline.m2_basis or Decimal(str(baseline.total_m2 or 0)) <= 0:
            errors.append({"code": "INVALID_PER_M2_BASIS", "message": "PER_M2 requires m2_basis and total_m2 > 0"})
        rate = Decimal(str((commercial.rate or {}).get("rate_per_m2") or 0))
        if not _eq(rate, Decimal(str((scenario.input_params or {}).get("rate_per_m2") or 0))):
            errors.append({"code": "RATE_MISMATCH", "message": "Commercial rate_per_m2 differs from selected pricing rate"})

    if mode == "PER_ROOM":
        if int(baseline.rooms_count or 0) <= 0:
            errors.append({"code": "INVALID_PER_ROOM_UNITS", "message": "PER_ROOM requires rooms_count > 0"})
    if mode == "PIECEWORK":
        if int(baseline.items_count or 0) <= 0:
            errors.append({"code": "INVALID_PIECEWORK_UNITS", "message": "PIECEWORK requires items_count > 0"})

    if mode == "HOURLY":
        lhs = Decimal(str((commercial.rate or {}).get("hourly_rate") or (commercial.rate or {}).get("hourly_rate_override") or 0))
        rhs = Decimal(str((scenario.input_params or {}).get("hourly_rate") or 0))
        if lhs and rhs and not _eq(lhs, rhs):
            errors.append({"code": "RATE_MISMATCH", "message": "Hourly rate differs from selected pricing rate"})

    if doc_type == DOC_TYPE_INVOICE and doc_id is not None:
        invoice = db.get(Invoice, doc_id)
        if invoice is None:
            errors.append({"code": "INVOICE_NOT_FOUND", "message": "Invoice not found"})
        else:
            if invoice.lines and not _eq(invoice.subtotal_ex_vat, scenario.price_ex_vat):
                errors.append({"code": "INVOICE_SUBTOTAL_MISMATCH", "message": "Invoice subtotal_ex_vat differs from pricing scenario"})
            if not _eq(invoice.subtotal_ex_vat, commercial.price_ex_vat):
                errors.append({"code": "INVOICE_COMMERCIAL_MISMATCH", "message": "Invoice subtotal differs from commercial total"})

    return ConsistencyResult(ok=len(errors) == 0, errors=errors, debug=debug)
