from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session, selectinload

from app.models.material_consumption_override import MaterialConsumptionOverride
from app.models.pricing_policy import get_or_create_pricing_policy
from app.models.project import Project, ProjectWorkItem
from app.models.settings import get_or_create_settings
from app.services.completeness import compute_completeness
from app.services.estimator_engine import (
    build_project_estimate,
    calculate_project_pricing_totals,
    compute_estimator_totals,
    recalculate_project_work_items,
)
from app.services.geometry import aggregate_project_geometry
from app.services.materials_bom import compute_project_bom
from app.services.pricing import WARNING_LOW_MARGIN, compute_pricing_scenarios, evaluate_floor, get_or_create_project_pricing
from app.services.pricing_consistency import DOC_TYPE_OFFER, validate_pricing_consistency
from app.services.quality import evaluate_project_quality


PRICING_MODE_ORDER = ["HOURLY", "PER_M2", "FIXED_TOTAL", "PER_ROOM", "PIECEWORK"]
SCENARIO_MODE_ORDER = PRICING_MODE_ORDER


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


def _basis_value(item: ProjectWorkItem, geometry: dict) -> Decimal:
    basis_map = {
        "floor_area_m2": _d(geometry.get("total_floor_area")),
        "wall_area_m2": _d(geometry.get("total_wall_area")),
        "ceiling_area_m2": _d(geometry.get("total_ceiling_area")),
    }
    return basis_map.get((item.basis_type or "").lower(), _d(item.calculated_qty))


def _build_item_warnings(item: ProjectWorkItem, rooms_count: int, geometry: dict) -> list[str]:
    warnings: list[str] = []
    if (item.scope_mode or "").upper() == "SELECTED_ROOMS" and not (item.selected_room_ids_json or "").strip():
        warnings.append("estimator.invalid.no_rooms_selected")
    if (item.scope_mode or "").upper() == "CUSTOM_QTY" and _d(item.manual_qty) <= 0:
        warnings.append("estimator.invalid.manual_qty_missing")
    if _d(item.norm_hours_per_unit) <= 0 and _d(getattr(item.work_type, "hours_per_unit", None)) <= 0:
        warnings.append("estimator.invalid.norm_hours_missing")
    if (item.pricing_mode or "").upper() == "FIXED_TOTAL" and _d(item.fixed_total_ex_vat or item.fixed_price_sek) <= 0:
        warnings.append("estimator.invalid.fixed_total_missing")
    if (item.pricing_mode or "").upper() in {"PER_M2", "PIECEWORK"} and _d(item.unit_rate_ex_vat or item.area_rate_sek) <= 0:
        warnings.append("estimator.invalid.unit_rate_missing")
    if rooms_count > 0 and (item.basis_type or "").lower() != "custom_qty" and _basis_value(item, geometry) <= 0:
        warnings.append("estimator.invalid.no_geometry")
    return list(dict.fromkeys(warnings))


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

    recalculate_project_work_items(db, project.id)

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
    active_mode = (pricing.mode or "HOURLY").upper()
    for scenario in scenarios:
        floor = evaluate_floor(baseline=baseline, scenario=scenario, policy=policy)
        mode = (scenario.mode or "").upper()
        pricing_scenarios[mode] = {
            "mode": mode,
            "revenue": _d(scenario.price_ex_vat),
            "cost": _d(baseline.internal_total_cost),
            "profit": _d(scenario.profit),
            "margin_pct": _d(scenario.margin_pct),
            "effective_hourly": _d(scenario.effective_hourly_sell_rate),
            "total": _d(scenario.price_inc_vat),
            "enabled": mode == active_mode,
            "invalid": bool(scenario.invalid),
            "missing_requirements": list(scenario.warnings if scenario.invalid else []),
            "below_margin_floor": bool(floor.is_below_floor),
            "warnings": list(scenario.warnings),
            "is_selected": mode == active_mode,
        }
        if WARNING_LOW_MARGIN in scenario.warnings:
            pricing_warnings.append(f"{mode}:LOW_MARGIN")

    for mode in SCENARIO_MODE_ORDER:
        pricing_scenarios.setdefault(
            mode,
            {
                "mode": mode,
                "revenue": Decimal("0.00"),
                "cost": Decimal("0.00"),
                "profit": Decimal("0.00"),
                "margin_pct": Decimal("0.00"),
                "effective_hourly": Decimal("0.00"),
                "total": Decimal("0.00"),
                "enabled": False,
                "invalid": True,
                "missing_requirements": ["MISSING_REQUIREMENTS"],
                "below_margin_floor": False,
                "warnings": ["MISSING_REQUIREMENTS"],
                "is_selected": False,
            },
        )

    for mode in SCENARIO_MODE_ORDER:
        pricing_scenarios[mode]["enabled"] = mode == active_mode
        pricing_scenarios[mode]["is_selected"] = mode == active_mode

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
    project_estimate = build_project_estimate(db, project_id)
    deterministic_modes = {"HOURLY", "PER_M2", "FIXED_TOTAL", "PIECEWORK"}
    for mode in PRICING_MODE_ORDER:
        scenario = pricing_scenarios[mode]
        row = {"mode": mode, **scenario, "missing_requirements": _build_missing_reasons(scenario)}
        if mode in deterministic_modes:
            mode_totals = calculate_project_pricing_totals(db, project_id, mode)
            row.update(
                {
                    "revenue": mode_totals.sell_ex_vat,
                    "cost": mode_totals.labour_cost_ex_vat + mode_totals.materials_ex_vat,
                    "profit": mode_totals.profit_ex_vat,
                    "margin_pct": mode_totals.margin_percent,
                    "effective_hourly": mode_totals.effective_hourly_ex_vat,
                    "total_hours": project_estimate.totals.total_hours,
                }
            )
        row["enabled"] = mode == (pricing.mode or "HOURLY").upper()
        row["invalid"] = bool(row.get("invalid") or row.get("missing_requirements"))
        row["reasons"] = row.get("missing_requirements", [])
        compare_rows.append(row)

    room_options = [{"id": room.id, "name": room.name} for room in rooms]
    work_item_rows = []
    for item in project.work_items:
        item_warnings = _build_item_warnings(item, len(rooms), {
            "total_floor_area": geometry.total_floor_area_m2,
            "total_wall_area": geometry.total_wall_area_net_m2,
            "total_ceiling_area": geometry.total_ceiling_area_m2,
        })
        work_item_rows.append({
            "id": item.id,
            "work_type_name": item.work_type.name_ru if item.work_type else "-",
            "scope_mode": (item.scope_mode or "ROOM").upper(),
            "basis_type": (item.basis_type or "floor_area_m2").lower(),
            "selected_room_ids": [int(v) for v in json.loads(item.selected_room_ids_json)] if item.selected_room_ids_json else [],
            "qty": _d(item.calculated_qty),
            "manual_qty": _d(item.manual_qty),
            "hours": _d(item.calculated_hours),
            "pricing_mode": (item.pricing_mode or "HOURLY").upper(),
            "sell_ex_vat": _d(item.calculated_sell_ex_vat),
            "fixed_total_ex_vat": _d(item.fixed_total_ex_vat),
            "unit_rate_ex_vat": _d(item.unit_rate_ex_vat),
            "hourly_rate_ex_vat": _d(item.hourly_rate_ex_vat),
            "invalid": bool(item_warnings),
            "reasons": item_warnings,
        })

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
            "rows": work_item_rows,
            "total_hours": project_estimate.totals.total_hours,
            "hours_by_room": {rooms_index.get(k).name if k in rooms_index else "project": v for k, v in hours_by_room.items()},
            "hours_by_work_type": dict(hours_by_work_type),
        },
        "totals": {
            "labour": totals.labour,
            "materials": totals.materials,
            "subtotal": totals.subtotal,
            "vat": totals.vat,
            "total": totals.total,
            "total_hours": project_estimate.totals.total_hours,
            "sell_ex_vat": project_estimate.totals.sell_ex_vat,
            "profit_ex_vat": project_estimate.totals.profit_ex_vat,
            "margin_percent": project_estimate.totals.margin_percent,
            "effective_hourly": project_estimate.totals.effective_hourly_ex_vat,
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
            "actual_total_cost": Decimal("0.00"),
            "override_applied": bool(source_badges - {"default"}),
            "warnings": list(bom.warnings),
        },
        "rooms": room_options,
        "active_mode": active_mode,
        "quality": {
            "completeness_score": completeness.score,
            "sanity_warnings": [issue.message for issue in quality.issues],
            "pricing_consistency_warnings": [err.get("code") for err in consistency.errors],
        },
    }


def calculate_project_total_hours_from_items(work_items: list[ProjectWorkItem]) -> Decimal:
    return sum((_d(item.calculated_hours) for item in work_items), Decimal("0")).quantize(Decimal("0.01"))
