from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_pricing import ProjectPricing
from app.services.geometry import aggregate_project_geometry
from app.services.material_costing import cost_project_materials

Q = Decimal("0.01")


@dataclass
class ProjectPricingSummary:
    labour_hours_total: Decimal
    labour_price_hourly: Decimal
    labour_price_per_m2: Decimal
    labour_price_fixed: Decimal
    materials_total: Decimal
    selected_mode: str
    selected_sell_price: Decimal
    selected_total_with_materials: Decimal
    basis_used: dict[str, str | Decimal]
    warnings: list[str]


def _q(value: Decimal) -> Decimal:
    return value.quantize(Q)


def _resolve_mode(pricing: ProjectPricing) -> str:
    mode = (pricing.pricing_mode or "").strip().lower()
    if mode in {"hourly", "per_m2", "fixed"}:
        return mode
    mode_map = {"HOURLY": "hourly", "PER_M2": "per_m2", "FIXED_TOTAL": "fixed"}
    return mode_map.get((pricing.mode or "HOURLY").upper(), "hourly")


def build_project_pricing_summary(project: Project, db: Session) -> ProjectPricingSummary:
    pricing = project.pricing or ProjectPricing(project_id=project.id)
    mode = _resolve_mode(pricing)
    warnings: list[str] = []

    labour_hours_total = _q(sum((Decimal(str(item.calculated_hours or 0)) for item in project.work_items), Decimal("0")))
    hourly_rate = Decimal(str(pricing.hourly_rate if pricing.hourly_rate is not None else pricing.hourly_rate_override or 0))
    sqm_rate = Decimal(str(pricing.sqm_rate if pricing.sqm_rate is not None else pricing.rate_per_m2 or 0))
    fixed_amount = Decimal(str(pricing.fixed_price_amount if pricing.fixed_price_amount is not None else pricing.fixed_total_price or 0))

    geometry = aggregate_project_geometry(db, project.id)
    sqm_basis = (pricing.sqm_basis or "walls_ceilings").lower()
    basis_value = Decimal("0")
    basis_label = sqm_basis
    if sqm_basis == "floor":
        basis_value = geometry.total_floor_area_m2
    elif sqm_basis == "walls":
        basis_value = geometry.total_wall_area_net_m2
    elif sqm_basis == "ceilings":
        basis_value = geometry.total_ceiling_area_m2
    elif sqm_basis == "custom":
        basis_value = Decimal(str(pricing.sqm_custom_value or 0))
        basis_label = "custom"
    else:
        basis_value = geometry.total_wall_area_net_m2 + geometry.total_ceiling_area_m2
        basis_label = "walls_ceilings"

    if mode == "hourly" and hourly_rate <= 0:
        warnings.append("pricing.validation.hourly_rate_required")
    if mode == "per_m2":
        if sqm_rate <= 0:
            warnings.append("pricing.validation.sqm_rate_required")
        if sqm_basis == "custom" and basis_value <= 0:
            warnings.append("pricing.validation.sqm_custom_required")
        if sqm_basis != "custom" and basis_value <= 0:
            warnings.append("pricing.validation.geometry_required")
    if mode == "fixed" and fixed_amount <= 0:
        warnings.append("pricing.validation.fixed_price_required")

    labour_price_hourly = _q(labour_hours_total * hourly_rate)
    labour_price_per_m2 = _q(basis_value * sqm_rate)
    labour_price_fixed = _q(fixed_amount)

    materials_total = Decimal("0.00")
    try:
        materials_total = _q(Decimal(str(cost_project_materials(db, project.id).total_ex_vat)))
    except Exception:
        warnings.append("pricing.warning.materials_unavailable")

    selected_sell = labour_price_hourly
    if mode == "per_m2":
        selected_sell = labour_price_per_m2
    if mode == "fixed":
        selected_sell = labour_price_fixed

    include_materials = pricing.include_materials_in_sell_price
    if include_materials is None:
        include_materials = pricing.include_materials
    total = selected_sell + materials_total if include_materials else selected_sell

    return ProjectPricingSummary(
        labour_hours_total=labour_hours_total,
        labour_price_hourly=labour_price_hourly,
        labour_price_per_m2=labour_price_per_m2,
        labour_price_fixed=labour_price_fixed,
        materials_total=materials_total,
        selected_mode=mode,
        selected_sell_price=_q(selected_sell),
        selected_total_with_materials=_q(total),
        basis_used={"basis": basis_label, "sqm": _q(basis_value), "rate": _q(sqm_rate)},
        warnings=warnings,
    )
