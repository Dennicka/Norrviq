from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session, selectinload

from app.models.material_consumption_override import MaterialConsumptionOverride
from app.models.project import Project, ProjectWorkItem
from app.services.completeness import compute_completeness
from app.services.estimator_engine import build_project_estimate
from app.services.estimates import calculate_project_total_hours, calculate_project_totals, recalculate_project_work_items
from app.services.geometry import aggregate_project_geometry
from app.services.materials_bom import compute_project_bom
from app.models.pricing_policy import get_or_create_pricing_policy
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
    estimate = build_project_estimate(db, project_id)

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

    total_hours = estimate["totals"]["total_hours"]

    baseline, scenarios = compute_pricing_scenarios(db, project_id)
    pricing = get_or_create_project_pricing(db, project_id)
    pricing_scenarios = {}
    pricing_warnings: list[str] = []
    policy = get_or_create_pricing_policy(db)
    scenario_key_map = {
        "HOURLY": "hourly",
        "PER_M2": "per_sqm",
        "PER_ROOM": "per_room",
        "PIECEWORK": "piecework",
        "FIXED_TOTAL": "fixed_price",
    }
    for scenario in scenarios:
        engine_row = estimate["pricing_scenarios"].get(scenario_key_map.get(scenario.mode, ""), {})
        floor = evaluate_floor(baseline=baseline, scenario=scenario, policy=policy)
        pricing_scenarios[scenario.mode] = {
            "mode": scenario.mode,
            "labour_amount": _d(engine_row.get("revenue", scenario.price_ex_vat)),
            "materials_amount": _d(baseline.materials_cost_internal),
            "subtotal": _d(engine_row.get("revenue", scenario.price_ex_vat)),
            "total": _d(engine_row.get("revenue", scenario.price_inc_vat)),
            "margin_pct": _d(engine_row.get("margin_percent", scenario.margin_pct)),
            "below_margin_floor": bool(floor.is_below_floor),
            "warnings": list(engine_row.get("missing_requirements", scenario.warnings)),
        }
        if WARNING_LOW_MARGIN in scenario.warnings:
            pricing_warnings.append(f"{scenario.mode}:LOW_MARGIN")

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
                "warning": "MISSING_PRICE" if has_missing_price else None,
            }
        )

    completeness = compute_completeness(db, project_id, mode=(pricing.mode or "HOURLY"), segment="OFFER", lang=lang)
    quality = evaluate_project_quality(db, project_id, lang=lang)
    consistency = validate_pricing_consistency(db, project_id, DOC_TYPE_OFFER)

    rooms_index = {room.id: room for room in rooms}
    return {
        "project": project,
        "geometry": {
            "rooms_count": len(rooms),
            "total_floor_area": estimate["scopes"]["floor_area_total"],
            "total_wall_area": estimate["scopes"]["wall_area_net_total"],
            "total_ceiling_area": estimate["scopes"]["ceiling_area_total"],
            "warnings": room_missing_geometry + estimate["warnings"],
        },
        "work_items": {
            "grouped": grouped_items,
            "total_hours": total_hours,
            "hours_by_room": {rooms_index.get(k).name if k in rooms_index else "project": v for k, v in hours_by_room.items()},
            "hours_by_work_type": dict(hours_by_work_type),
        },
        "pricing": {
            "selected_mode": pricing.mode,
            "scenarios": pricing_scenarios,
            "warnings": pricing_warnings,
        },
        "estimate": estimate,
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
