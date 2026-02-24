from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session, selectinload

from app.models.project import Project, ProjectWorkItem
from app.models.settings import get_or_create_settings
from app.models.worktype import WorkType
from app.services.geometry import compute_room_geometry_from_model
from app.services.pricing import compute_pricing_scenarios, get_or_create_project_pricing

MONEY = Decimal("0.01")
QTY = Decimal("0.0001")


def _d(value: object | None) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


def _m(value: Decimal) -> Decimal:
    return value.quantize(MONEY)


def _q(value: Decimal) -> Decimal:
    return value.quantize(QTY)


def _measurement_basis(item: ProjectWorkItem) -> str:
    work_type: WorkType | None = item.work_type
    unit = (work_type.unit if work_type else "").lower()
    code = (work_type.code if work_type else "").lower()
    label = f"{code} {(work_type.name_ru if work_type else '')} {(work_type.name_sv if work_type else '')}".lower()
    if unit == "m":
        return "perimeter"
    if unit in {"room"}:
        return "room"
    if unit in {"piece", "window", "door", "radiator"}:
        return "piece"
    if unit == "m2":
        if any(token in label for token in ("ceiling", "потол", "tak")):
            return "ceiling"
        if any(token in label for token in ("floor", "пол", "golv")):
            return "floor"
        return "walls"
    return "manual"


def _room_geometry_map(project: Project) -> tuple[dict[int, dict], list[str]]:
    room_map: dict[int, dict] = {}
    warnings: list[str] = []
    for room in project.rooms:
        geometry = compute_room_geometry_from_model(room)
        for warning in geometry.warnings:
            warnings.append(f"room:{room.id}:{warning}")
        room_map[room.id] = {
            "floor": _d(geometry.floor_area_m2),
            "ceiling": _d(geometry.ceiling_area_m2),
            "walls": _d(geometry.wall_area_gross_m2),
            "walls_net": _d(geometry.wall_area_net_m2),
            "perimeter": _d(geometry.perimeter_m),
        }
    return room_map, warnings


def _line_quantity(item: ProjectWorkItem, room_geometry: dict[int, dict], room_count: int) -> tuple[Decimal, list[str]]:
    basis = _measurement_basis(item)
    warnings: list[str] = []
    if basis == "manual":
        return _d(item.quantity), warnings
    if basis == "room":
        return Decimal("1") if item.room_id else Decimal(room_count), warnings
    if basis == "piece":
        return _d(item.quantity) if _d(item.quantity) > 0 else Decimal("1"), warnings

    if item.room_id is not None:
        geometry = room_geometry.get(item.room_id) or {}
        value = _d(geometry.get(basis))
        if value <= 0:
            warnings.append(f"MISSING_{basis.upper()}_AREA")
        return value, warnings

    value = sum((_d(room.get(basis)) for room in room_geometry.values()), Decimal("0"))
    if value <= 0:
        warnings.append(f"MISSING_{basis.upper()}_AREA")
    return value, warnings


def build_project_estimate(db: Session, project_id: int) -> dict:
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
        raise ValueError("Project not found")

    settings = get_or_create_settings(db)
    pricing = get_or_create_project_pricing(db, project_id)
    hourly_cost = _d(pricing.hourly_rate_override or settings.default_worker_hourly_rate or settings.hourly_rate_company)

    room_geometry, warnings = _room_geometry_map(project)
    scopes = {
        "floor_area_total": _q(sum((_d(v["floor"]) for v in room_geometry.values()), Decimal("0"))),
        "ceiling_area_total": _q(sum((_d(v["ceiling"]) for v in room_geometry.values()), Decimal("0"))),
        "wall_area_total": _q(sum((_d(v["walls"]) for v in room_geometry.values()), Decimal("0"))),
        "wall_area_net_total": _q(sum((_d(v["walls_net"]) for v in room_geometry.values()), Decimal("0"))),
        "perimeter_total": _q(sum((_d(v["perimeter"]) for v in room_geometry.values()), Decimal("0"))),
        "room_count": len(project.rooms),
    }

    lines: list[dict] = []
    total_hours = Decimal("0")
    labour_cost = Decimal("0")
    materials_cost = Decimal("0")
    for item in project.work_items:
        quantity_base, line_warnings = _line_quantity(item, room_geometry, len(project.rooms))
        layers_multiplier = _d(item.quantity) if _d(item.quantity) > 0 else Decimal("1")
        quantity_final = _q(quantity_base * layers_multiplier)
        norm = _d(item.work_type.hours_per_unit if item.work_type else 0)
        estimated_hours = _d(item.calculated_hours)
        if estimated_hours <= 0 and norm > 0:
            estimated_hours = _q(quantity_final * norm)
            line_warnings.append("HOURS_DERIVED_FROM_NORM")

        line_labour_cost = _m(estimated_hours * hourly_cost)
        total_hours += estimated_hours
        labour_cost += line_labour_cost
        materials_cost += _d(item.materials_cost_sek)

        room_name = item.room.name if item.room else "Project"
        worktype_name = item.work_type.name_ru if item.work_type else "-"
        lines.append(
            {
                "id": item.id,
                "room_id": item.room_id,
                "room_name": room_name,
                "worktype_id": item.work_type_id,
                "worktype_name": worktype_name,
                "measurement_basis": _measurement_basis(item),
                "quantity_base": _q(quantity_base),
                "layers_multiplier": _q(layers_multiplier),
                "quantity_final": quantity_final,
                "norm_per_hour_or_prod_rate": _q(norm),
                "estimated_hours": _q(estimated_hours),
                "hourly_cost": _m(hourly_cost),
                "line_labour_cost": line_labour_cost,
                "warnings": line_warnings,
            }
        )

    materials_cost = _m(materials_cost)
    total_hours = _q(total_hours)
    labour_cost = _m(labour_cost)
    total_cost = _m(labour_cost + materials_cost)

    _, raw_scenarios = compute_pricing_scenarios(db, project_id)
    scenarios: dict[str, dict] = {}
    mode_map = {
        "HOURLY": "hourly",
        "PER_M2": "per_sqm",
        "PER_ROOM": "per_room",
        "PIECEWORK": "piecework",
        "FIXED_TOTAL": "fixed_price",
    }
    has_m2_blocker = any(("периметр" in w.lower()) or ("высоты" in w.lower()) or ("wall_area" in w.lower()) for w in warnings)
    for sc in raw_scenarios:
        key = mode_map.get(sc.mode)
        if not key:
            continue
        forced_invalid = key == "per_sqm" and has_m2_blocker
        missing = list(sc.warnings) if sc.invalid else []
        if forced_invalid and "MISSING_UNITS_M2" not in missing:
            missing.append("MISSING_UNITS_M2")
        scenarios[key] = {
            "enabled": (not sc.invalid) and (not forced_invalid),
            "missing_requirements": missing,
            "revenue": _m(_d(sc.price_ex_vat)),
            "cost": total_cost,
            "gross_profit": _m(_d(sc.price_ex_vat) - total_cost),
            "margin_percent": _q(_d(sc.margin_pct)) if sc.margin_pct is not None else None,
        }

    for required in ("hourly", "per_sqm", "per_room", "piecework", "fixed_price"):
        scenarios.setdefault(required, {"enabled": False, "missing_requirements": ["SCENARIO_NOT_AVAILABLE"], "revenue": Decimal("0.00"), "cost": total_cost, "gross_profit": Decimal("0.00"), "margin_percent": None})

    readiness = {
        "can_price_hourly": scenarios["hourly"]["enabled"],
        "can_price_per_sqm": scenarios["per_sqm"]["enabled"],
        "can_price_fixed": scenarios["fixed_price"]["enabled"],
        "can_issue_offer": all(scenarios[m]["enabled"] for m in ("hourly", "fixed_price")),
    }

    if scopes["wall_area_total"] <= 0:
        warnings.append("PROJECT_MISSING_WALL_AREA")

    return {
        "project": {"id": project.id, "name": project.name},
        "totals": {
            "total_hours": total_hours,
            "labour_cost": labour_cost,
            "materials_cost_planned": materials_cost,
            "total_cost": total_cost,
        },
        "scopes": scopes,
        "lines": lines,
        "pricing_scenarios": scenarios,
        "warnings": warnings,
        "readiness": readiness,
    }
