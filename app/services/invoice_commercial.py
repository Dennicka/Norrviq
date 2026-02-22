from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session, selectinload

from app.models.invoice import Invoice
from app.models.project import Project
from app.models.rot_case import RotCase
from app.models.settings import get_or_create_settings
from app.services.offer_commercial import _basis_label
from app.services.pricing import compute_pricing_scenarios

MONEY = Decimal("0.01")


@dataclass
class InvoiceCommercial:
    mode: str
    units: dict
    rate: dict
    price_ex_vat: Decimal
    vat_amount: Decimal
    price_inc_vat: Decimal
    line_items: list[dict]
    vat_rot_breakdown: dict
    warnings: list[str]


def _q(value: Decimal) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _line_items(mode: str, selected, baseline, lang: str) -> list[dict]:
    if mode == "FIXED_TOTAL":
        return [{"description": "Fast pris – arbete", "kind": "LABOR", "qty": Decimal("1.00"), "unit": "st", "unit_price": selected.price_ex_vat, "total": selected.price_ex_vat}]
    if mode == "PER_M2":
        qty = _q(Decimal(str(baseline.total_m2 or 0)))
        unit_price = _q(Decimal(str(selected.input_params.get("rate_per_m2") or 0)))
        return [{"description": f"Målning {_basis_label(lang, baseline.m2_basis)}", "kind": "LABOR", "qty": qty, "unit": "m²", "unit_price": unit_price, "total": _q(qty * unit_price)}]
    if mode == "PER_ROOM":
        qty = Decimal(str(baseline.rooms_count or 0))
        unit_price = _q(Decimal(str(selected.input_params.get("rate_per_room") or 0)))
        return [{"description": "Målning per rum", "kind": "LABOR", "qty": qty, "unit": "rum", "unit_price": unit_price, "total": _q(qty * unit_price)}]
    if mode == "PIECEWORK":
        qty = Decimal(str(baseline.items_count or 0))
        unit_price = _q(Decimal(str(selected.input_params.get("rate_per_piece") or 0)))
        return [{"description": "Arbete enligt styckpris", "kind": "LABOR", "qty": qty, "unit": "st", "unit_price": unit_price, "total": _q(qty * unit_price)}]
    return []


def compute_invoice_commercial(db: Session, project_id: int, invoice_id: int | None = None, *, lang: str = "sv") -> InvoiceCommercial:
    project = (
        db.query(Project)
        .options(selectinload(Project.pricing), selectinload(Project.client))
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise ValueError("Project not found")

    baseline, scenarios = compute_pricing_scenarios(db, project_id)
    mode = (project.pricing.mode if project.pricing else "HOURLY").upper()
    selected = next((s for s in scenarios if s.mode == mode), scenarios[0])

    settings = get_or_create_settings(db)
    vat_pct = _q(Decimal(str(settings.moms_percent if settings.moms_percent is not None else 25)))
    vat_amount = _q(selected.price_ex_vat * vat_pct / Decimal("100"))
    price_inc_vat = _q(selected.price_ex_vat + vat_amount)

    labour_ex = selected.price_ex_vat
    material_ex = Decimal("0.00")
    other_ex = Decimal("0.00")
    rot_enabled = False
    rot_pct = Decimal("0.00")
    rot_amount = Decimal("0.00")
    if invoice_id:
        rot_case = db.query(RotCase).filter(RotCase.invoice_id == invoice_id).first()
        invoice = db.get(Invoice, invoice_id)
        if invoice and invoice.status == "issued":
            rot_enabled = bool(invoice.rot_snapshot_enabled)
            rot_pct = _q(Decimal(str(invoice.rot_snapshot_pct or 0)))
            rot_amount = _q(Decimal(str(invoice.rot_snapshot_amount or 0)))
        elif rot_case:
            rot_enabled = bool(rot_case.is_enabled)
            rot_pct = _q(Decimal(str(rot_case.rot_pct or 0)))
            rot_amount = _q(labour_ex * rot_pct / Decimal("100")) if rot_enabled else Decimal("0.00")

    return InvoiceCommercial(
        mode=mode,
        units={
            "m2_basis": baseline.m2_basis,
            "m2_basis_label": _basis_label(lang, baseline.m2_basis),
            "total_m2": baseline.total_m2,
            "rooms_count": baseline.rooms_count,
            "items_count": baseline.items_count,
        },
        rate={
            "hourly_rate_override": selected.input_params.get("hourly_rate"),
            "fixed_total_price": selected.input_params.get("fixed_total_price"),
            "rate_per_m2": selected.input_params.get("rate_per_m2"),
            "rate_per_room": selected.input_params.get("rate_per_room"),
            "rate_per_piece": selected.input_params.get("rate_per_piece"),
        },
        price_ex_vat=selected.price_ex_vat,
        vat_amount=vat_amount,
        price_inc_vat=price_inc_vat,
        line_items=_line_items(mode, selected, baseline, lang),
        warnings=list(selected.warnings),
        vat_rot_breakdown={
            "vat_rate_pct": vat_pct,
            "labour_ex_vat": _q(labour_ex),
            "material_ex_vat": _q(material_ex),
            "other_ex_vat": _q(other_ex),
            "rot_enabled": rot_enabled,
            "rot_pct": rot_pct,
            "rot_amount": rot_amount,
            "payable_total": _q(price_inc_vat - rot_amount),
        },
    )


def serialize_invoice_commercial(commercial: InvoiceCommercial) -> str:
    def norm(v):
        if isinstance(v, Decimal):
            return str(_q(v))
        if isinstance(v, list):
            return [norm(x) for x in v]
        if isinstance(v, dict):
            return {k: norm(val) for k, val in v.items()}
        return v

    return json.dumps(norm(commercial.__dict__), ensure_ascii=False, sort_keys=True)
