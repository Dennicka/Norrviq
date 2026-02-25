from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.models.project import Project

MONEY_Q = Decimal("0.01")


@dataclass
class EstimatorTotals:
    total_hours: Decimal
    labour: Decimal
    materials: Decimal
    subtotal: Decimal
    vat: Decimal
    total: Decimal


def _q(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def compute_estimator_totals(*, project: Project, materials_ex_vat: Decimal, vat_percent: Decimal) -> EstimatorTotals:
    total_hours = _q(sum((Decimal(str(item.calculated_hours or 0)) for item in project.work_items), Decimal("0")))
    labour = _q(sum((Decimal(str(item.calculated_cost_without_moms or 0)) for item in project.work_items), Decimal("0")))
    materials = _q(Decimal(str(materials_ex_vat or 0)))
    subtotal = _q(labour + materials)
    vat = _q(subtotal * (Decimal(str(vat_percent or 0)) / Decimal("100")))
    return EstimatorTotals(
        total_hours=total_hours,
        labour=labour,
        materials=materials,
        subtotal=subtotal,
        vat=vat,
        total=_q(subtotal + vat),
    )
