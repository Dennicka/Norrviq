from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session, selectinload

from app.models.material_consumption_override import MaterialConsumptionOverride
from app.models.pricing_policy import get_or_create_pricing_policy
from app.models.project import Project, ProjectWorkItem
from app.models.settings import get_or_create_settings
from app.services.completeness import compute_completeness
from app.services.estimator_engine import compute_estimator_totals
from app.services.estimates import calculate_project_totals, recalculate_project_work_items
from app.services.geometry import aggregate_project_geometry
from app.services.materials_bom import compute_project_bom
from app.services.pricing import WARNING_LOW_MARGIN, compute_pricing_scenarios, evaluate_floor, get_or_create_project_pricing
from app.services.pricing_consistency import DOC_TYPE_OFFER, validate_pricing_consistency
from app.services.quality import evaluate_project_quality


def _d(value: Decimal | None) -> Decimal:
    return Decimal(str(value or 0))


def _apply_source_badge(raw: str) -> str:
    if "room_override" in raw:
        return "room_override"
    if "project_override" in raw:
        return "project_override"
    return "default"


def _build_missing_reasons(scenario: dict) -> list[str]:
    reasons = list(scenario.get("warnings") or [])
    if not scenario.get("enabled", True) and not reasons:
        reasons.append("MISSING_REQUIREMENTS")
    return reasons


def build_estimator_workspace(db: Session, project_id: int, lang: str = "ru") -> dict:
    project = (
        db.query(Project)
        .options(
            selectinload(Project.rooms),
            selectinload(Project.work_items).selectinload(ProjectWorkItem.work_type),
            selectinload(Project.pricing),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        return {}

    recalculate_project_work_items(db, project)
    calculate_project_totals(db, project)

    geometry = aggregate_project_geometry(db, project_id)
    rooms = list(project.rooms)
    room_missing_geometry = [r.name for r in rooms if _d(r.floor_area_m2) <= 0 or _d(r.wall_area_m2) <= 0 or _d(r.ceiling_area_m2) <= 0]

    grouped_items: dict[int | None, list[ProjectWorkItem]] = defaultdict(list)
    hours_by_room: dict[int | None, Decimal] = defaultdict(lambda: Decimal("0"))
    hours_by_work_type: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in project.work_items:
        grouped_items[item.room_id].append(item)
        item_hours = _d(item.calculated_hours)
        hours_by_room[item.room_id] += item_hours
        wt_key = (item.work_type.name_ru if item.work_type else "-")
        hours_by_work_type[wt_key] += item_hours

    baseline, scenarios = compute_pricing_scenarios(db, project_id)
    pricing = get_or_create_project_pricing(db, project_id)
    pricing_scenarios: dict[str, dict] = {}
    pricing_warnings: list[str] = []
    policy = get_or_create_pricing_policy(db)
    for scenario in scenarios:
        floor = evaluate_floor(baseline=baseline, scenario=scenario, policy=policy)
        pricing_scenarios[scenario.mode] = {
            "mode": scenario.mode,
            "revenue": _d(scenario.price_ex_vat),
            "cost": _d(baseline.internal_total_cost),
            "profit": _d(scenario.profit),
            "margin_pct": _d(scenario.margin_pct),
            "effective_hourly": _d(scenario.effective_hourly_sell_rate),
            "total": _d(scenario.price_inc_vat),
            "enabled": not scenario.invalid,
            "missing_requirements": list(scenario.warnings if scenario.invalid else []),
            "below_margin_floor": bool(floor.is_below_floor),
            "warnings": list(scenario.warnings),
            "is_selected": scenario.mode == pricing.mode,
        }
        if WARNING_LOW_MARGIN in scenario.warnings:
            pricing_warnings.append(f"{scenario.mode}:LOW_MARGIN")

    # Lightweight hybrid scenario: safe visible compare based on best available mode.
    enabled_modes = [row for row in pricing_scenarios.values() if row["enabled"]]
    if enabled_modes:
        hybrid = max(enabled_modes, key=lambda row: row["profit"])
        pricing_scenarios["HYBRID"] = {
            "mode": "HYBRID",
            "revenue": hybrid["revenue"],
            "cost": hybrid["cost"],
            "profit": hybrid["profit"],
            "margin_pct": hybrid["margin_pct"],
            "effective_hourly": hybrid["effective_hourly"],
            "total": hybrid["total"],
            "enabled": True,
            "missing_requirements": [],
            "below_margin_floor": hybrid["below_margin_floor"],
            "warnings": [f"BLEND_FROM:{hybrid['mode']}"] + hybrid["warnings"],
            "is_selected": pricing.mode == "HYBRID",
        }

    bom = compute_project_bom(db, project_id)
    material_rows = []
    room_override_exists = db.query(MaterialConsumptionOverride).filter(MaterialConsumptionOverride.project_id == project_id, MaterialConsumptionOverride.room_id.isnot(None), MaterialConsumptionOverride.is_active.is_(True)).first() is not None
    project_override_exists = db.query(MaterialConsumptionOverride).filter(MaterialConsumptionOverride.project_id == project_id, MaterialConsumptionOverride.room_id.is_(None), MaterialConsumptionOverride.is_active.is_(True)).first() is not None
    source_badges = set()
    for item in bom.items:
        source_hint = "room_override" if room_override_exists else ("project_override" if project_override_exists else _apply_source_badge(item.norm_label))
        source_badges.add(source_hint)
        has_missing_price = _d(item.cost_ex_vat) <= 0
        material_rows.append(
            {
                "name": item.name,
                "quantity": _d(item.qty_final_unit),
                "unit": item.unit,
                "source": source_hint,
                "estimated_cost": _d(item.cost_ex_vat),
                "waste_percent": _d(item.waste_percent),
                "layers_multiplier": _d(item.coats),
                "warning": "MISSING_PRICE" if has_missing_price else None,
            }
        )

    settings = get_or_create_settings(db)
    totals = compute_estimator_totals(
        project=project,
        materials_ex_vat=_d(bom.total_cost_ex_vat),
        vat_percent=Decimal(str(settings.moms_percent or 0)),
    )

    completeness = compute_completeness(db, project_id, mode=(pricing.mode or "HOURLY"), segment="OFFER", lang=lang)
    quality = evaluate_project_quality(db, project_id, lang=lang)
    consistency = validate_pricing_consistency(db, project_id, DOC_TYPE_OFFER)

    rooms_index = {room.id: room for room in rooms}
    compare_rows = []
    for mode, scenario in pricing_scenarios.items():
        row = {"mode": mode, **scenario, "missing_requirements": _build_missing_reasons(scenario)}
        compare_rows.append(row)

    return {
        "project": project,
        "geometry": {
            "rooms_count": len(rooms),
            "total_floor_area": _d(geometry.total_floor_area_m2),
            "total_wall_area": _d(geometry.total_wall_area_net_m2),
            "total_ceiling_area": _d(geometry.total_ceiling_area_m2),
            "warnings": room_missing_geometry,
        },
        "work_items": {
            "grouped": grouped_items,
            "total_hours": totals.total_hours,
            "hours_by_room": {rooms_index.get(k).name if k in rooms_index else "project": v for k, v in hours_by_room.items()},
            "hours_by_work_type": dict(hours_by_work_type),
        },
        "totals": {
            "labour": totals.labour,
            "materials": totals.materials,
            "subtotal": totals.subtotal,
            "vat": totals.vat,
            "total": totals.total,
            "total_hours": totals.total_hours,
        },
        "pricing": {
            "selected_mode": pricing.mode,
            "scenarios": pricing_scenarios,
            "compare_rows": compare_rows,
            "warnings": pricing_warnings,
        },
        "materials": {
            "rows": material_rows,
            "total_estimated_cost": _d(bom.total_cost_ex_vat),
            "override_applied": bool(source_badges - {"default"}),
            "warnings": list(bom.warnings),
        },
        "quality": {
            "completeness_score": completeness.score,
            "sanity_warnings": [issue.message for issue in quality.issues],
            "pricing_consistency_warnings": [err.get("code") for err in consistency.errors],
        },
    }


def calculate_project_total_hours_from_items(work_items: list[ProjectWorkItem]) -> Decimal:
    return sum((_d(item.calculated_hours) for item in work_items), Decimal("0")).quantize(Decimal("0.01"))
