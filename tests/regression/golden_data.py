from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.buffer_rule import BufferRule
from app.models.cost import CostCategory, ProjectCostItem
from app.models.pricing_policy import PricingPolicy, get_or_create_pricing_policy
from app.models.project import Project, ProjectWorkItem, ProjectWorkerAssignment
from app.models.room import Room
from app.models.settings import get_or_create_settings
from app.models.project_takeoff_settings import ProjectTakeoffSettings
from app.models.worker import Worker
from app.models.worktype import WorkType
from app.services.estimates import calculate_work_item
from app.services.pricing import DesiredInput, compute_conversions, compute_pricing_scenarios, evaluate_floor, get_or_create_project_pricing

GOLDEN_DIR = Path("tests/golden")
GOLDEN_CASES = ("g1_small_room", "g2_apartment", "g3_missing_units", "g4_large", "g5_paintable_basis")


def _decimal_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _norm(value):
    if isinstance(value, Decimal):
        return _decimal_str(value)
    if isinstance(value, dict):
        return {k: _norm(v) for k, v in sorted(value.items(), key=lambda item: item[0])}
    if isinstance(value, list):
        return [_norm(v) for v in value]
    return value


def _ensure_category(db: Session, code: str, name: str) -> CostCategory:
    category = db.query(CostCategory).filter(CostCategory.code == code).first()
    if category:
        return category
    category = CostCategory(code=code, name_ru=name, name_sv=name)
    db.add(category)
    db.flush()
    return category


def _make_work_type(db: Session, suffix: str, *, unit: str, hours_per_unit: Decimal) -> WorkType:
    code = f"GT-{suffix}"
    existing = db.query(WorkType).filter(WorkType.code == code).first()
    if existing:
        return existing

    wt = WorkType(
        code=code,
        category="golden",
        unit=unit,
        name_ru=f"Golden {suffix}",
        name_sv=f"Golden {suffix}",
        description_ru=None,
        description_sv=None,
        hours_per_unit=hours_per_unit,
        base_difficulty_factor=Decimal("1.00"),
        is_active=True,
    )
    db.add(wt)
    db.flush()
    return wt


def _add_item(
    db: Session,
    *,
    project: Project,
    room: Room | None,
    work_type: WorkType,
    quantity: Decimal,
    difficulty: Decimal,
    company_rate: Decimal,
) -> None:
    item = ProjectWorkItem(
        project_id=project.id,
        room_id=room.id if room else None,
        work_type_id=work_type.id,
        quantity=quantity,
        difficulty_factor=difficulty,
    )
    calculate_work_item(item, work_type, company_rate)
    db.add(item)


def _configure_defaults(db: Session) -> None:
    settings = get_or_create_settings(db)
    settings.hourly_rate_company = Decimal("550.00")
    settings.default_worker_hourly_rate = Decimal("180.00")
    settings.employer_contributions_percent = Decimal("31.42")
    settings.default_overhead_percent = Decimal("10.00")
    settings.moms_percent = Decimal("25.00")

    policy = get_or_create_pricing_policy(db)
    policy.min_margin_pct = Decimal("15.00")
    policy.min_profit_sek = Decimal("1000.00")
    policy.min_effective_hourly_ex_vat = Decimal("500.00")
    db.commit()


def _populate_case(db: Session, case_name: str) -> tuple[int, Decimal, Decimal]:
    company_rate = Decimal("550.00")
    project = Project(name=f"Golden {case_name}")
    db.add(project)
    db.flush()

    mat = _ensure_category(db, "MATERIALS", "Материалы")
    other = _ensure_category(db, "OTHER", "Прочее")
    travel = _ensure_category(db, "TRAVEL", "Транспорт")

    if case_name == "g1_small_room":
        wt_wall = _make_work_type(db, "G1-WALL", unit="m2", hours_per_unit=Decimal("1.50"))
        wt_door = _make_work_type(db, "G1-DOOR", unit="piece", hours_per_unit=Decimal("0.50"))
        room = Room(project_id=project.id, name="Small room", floor_area_m2=Decimal("12.50"))
        db.add(room)
        db.flush()
        _add_item(db, project=project, room=room, work_type=wt_wall, quantity=Decimal("6.00"), difficulty=Decimal("1.00"), company_rate=company_rate)
        _add_item(db, project=project, room=room, work_type=wt_door, quantity=Decimal("2.00"), difficulty=Decimal("1.10"), company_rate=company_rate)

        worker = Worker(name="Golden G1 Worker", hourly_rate=Decimal("220.00"), is_active=True)
        db.add(worker)
        db.flush()
        db.add(ProjectWorkerAssignment(project_id=project.id, worker_id=worker.id, planned_hours=Decimal("10.10"), actual_hours=Decimal("10.10")))
        db.add(ProjectCostItem(project_id=project.id, cost_category_id=mat.id, title="Paint", amount=Decimal("350.00"), is_material=True))
        db.add(ProjectCostItem(project_id=project.id, cost_category_id=travel.id, title="Travel", amount=Decimal("120.00"), is_material=False))

        desired_hourly = Decimal("780.00")
        target_margin = Decimal("28.00")
    elif case_name == "g2_apartment":
        wt_wall = _make_work_type(db, "G2-WALL", unit="m2", hours_per_unit=Decimal("1.20"))
        wt_ceiling = _make_work_type(db, "G2-CEIL", unit="m2", hours_per_unit=Decimal("0.70"))
        wt_trim = _make_work_type(db, "G2-TRIM", unit="m", hours_per_unit=Decimal("0.35"))
        rooms = [
            Room(project_id=project.id, name="Living", floor_area_m2=Decimal("24.00")),
            Room(project_id=project.id, name="Bedroom", floor_area_m2=Decimal("16.00")),
            Room(project_id=project.id, name="Kitchen", floor_area_m2=Decimal("12.00")),
        ]
        db.add_all(rooms)
        db.flush()
        _add_item(db, project=project, room=rooms[0], work_type=wt_wall, quantity=Decimal("18.00"), difficulty=Decimal("1.00"), company_rate=company_rate)
        _add_item(db, project=project, room=rooms[0], work_type=wt_ceiling, quantity=Decimal("20.00"), difficulty=Decimal("1.05"), company_rate=company_rate)
        _add_item(db, project=project, room=rooms[1], work_type=wt_wall, quantity=Decimal("14.00"), difficulty=Decimal("1.10"), company_rate=company_rate)
        _add_item(db, project=project, room=rooms[1], work_type=wt_trim, quantity=Decimal("30.00"), difficulty=Decimal("1.00"), company_rate=company_rate)
        _add_item(db, project=project, room=rooms[2], work_type=wt_wall, quantity=Decimal("10.00"), difficulty=Decimal("1.15"), company_rate=company_rate)
        _add_item(db, project=project, room=rooms[2], work_type=wt_ceiling, quantity=Decimal("12.00"), difficulty=Decimal("1.00"), company_rate=company_rate)

        worker_a = Worker(name="Golden G2 Worker A", hourly_rate=Decimal("210.00"), is_active=True)
        worker_b = Worker(name="Golden G2 Worker B", hourly_rate=Decimal("240.00"), is_active=True)
        db.add_all([worker_a, worker_b])
        db.flush()
        db.add_all(
            [
                ProjectWorkerAssignment(project_id=project.id, worker_id=worker_a.id, planned_hours=Decimal("38.00"), actual_hours=Decimal("38.00")),
                ProjectWorkerAssignment(project_id=project.id, worker_id=worker_b.id, planned_hours=Decimal("22.00"), actual_hours=Decimal("22.00")),
            ]
        )
        db.add_all(
            [
                ProjectCostItem(project_id=project.id, cost_category_id=mat.id, title="Materials", amount=Decimal("1800.00"), is_material=True),
                ProjectCostItem(project_id=project.id, cost_category_id=travel.id, title="Travel", amount=Decimal("420.00"), is_material=False),
                ProjectCostItem(project_id=project.id, cost_category_id=other.id, title="Waste", amount=Decimal("250.00"), is_material=False),
            ]
        )

        desired_hourly = Decimal("900.00")
        target_margin = Decimal("35.00")
    elif case_name == "g3_missing_units":
        wt_piece = _make_work_type(db, "G3-PIECE", unit="piece", hours_per_unit=Decimal("2.50"))
        _add_item(db, project=project, room=None, work_type=wt_piece, quantity=Decimal("4.00"), difficulty=Decimal("1.00"), company_rate=company_rate)

        worker = Worker(name="Golden G3 Worker", hourly_rate=Decimal("200.00"), is_active=True)
        db.add(worker)
        db.flush()
        db.add(ProjectWorkerAssignment(project_id=project.id, worker_id=worker.id, planned_hours=Decimal("11.00"), actual_hours=Decimal("11.00")))
        db.add(ProjectCostItem(project_id=project.id, cost_category_id=other.id, title="Misc", amount=Decimal("150.00"), is_material=False))

        desired_hourly = Decimal("760.00")
        target_margin = Decimal("20.00")
    elif case_name == "g4_large":
        wt_main = _make_work_type(db, "G4-MAIN", unit="m2", hours_per_unit=Decimal("0.80"))
        wt_trim = _make_work_type(db, "G4-TRIM", unit="m", hours_per_unit=Decimal("0.20"))
        rooms = []
        for i in range(20):
            room = Room(project_id=project.id, name=f"R-{i+1}", floor_area_m2=Decimal("15.00") + Decimal(i % 5))
            rooms.append(room)
        db.add_all(rooms)
        db.flush()

        for i in range(54):
            room = rooms[i % len(rooms)]
            if i % 2 == 0:
                _add_item(db, project=project, room=room, work_type=wt_main, quantity=Decimal("8.00") + Decimal(i % 3), difficulty=Decimal("1.00"), company_rate=company_rate)
            else:
                _add_item(db, project=project, room=room, work_type=wt_trim, quantity=Decimal("20.00") + Decimal(i % 4), difficulty=Decimal("1.05"), company_rate=company_rate)

        worker = Worker(name="Golden G4 Worker", hourly_rate=Decimal("215.00"), is_active=True)
        db.add(worker)
        db.flush()
        db.add(ProjectWorkerAssignment(project_id=project.id, worker_id=worker.id, planned_hours=Decimal("260.00"), actual_hours=Decimal("260.00")))
        db.add_all(
            [
                ProjectCostItem(project_id=project.id, cost_category_id=mat.id, title="Bulk materials", amount=Decimal("5600.00"), is_material=True),
                ProjectCostItem(project_id=project.id, cost_category_id=travel.id, title="Logistics", amount=Decimal("1400.00"), is_material=False),
                ProjectCostItem(project_id=project.id, cost_category_id=other.id, title="Waste", amount=Decimal("900.00"), is_material=False),
            ]
        )

        desired_hourly = Decimal("860.00")
        target_margin = Decimal("32.00")
    elif case_name == "g5_paintable_basis":
        wt_wall = _make_work_type(db, "G5-WALL", unit="m2", hours_per_unit=Decimal("1.00"))
        room = Room(project_id=project.id, name="Paint room", floor_area_m2=Decimal("20.00"), wall_perimeter_m=Decimal("18.00"), wall_height_m=Decimal("2.50"))
        db.add(room)
        db.flush()
        _add_item(db, project=project, room=room, work_type=wt_wall, quantity=Decimal("10.00"), difficulty=Decimal("1.00"), company_rate=company_rate)
        db.add(ProjectCostItem(project_id=project.id, cost_category_id=mat.id, title="Paint", amount=Decimal("200.00"), is_material=True))
        desired_hourly = Decimal("700.00")
        target_margin = Decimal("25.00")
    else:
        raise ValueError(f"Unknown golden case: {case_name}")

    db.flush()
    pricing = get_or_create_project_pricing(db, project.id)
    pricing.hourly_rate_override = Decimal("640.00")
    pricing.fixed_total_price = Decimal("9900.00")
    pricing.rate_per_m2 = Decimal("280.00")
    pricing.rate_per_room = Decimal("3200.00")
    pricing.rate_per_piece = Decimal("1150.00")
    pricing.target_margin_pct = Decimal("30.00")
    pricing.include_materials = True
    pricing.include_travel_setup_buffers = True
    if case_name == "g5_paintable_basis":
        takeoff = db.query(ProjectTakeoffSettings).filter(ProjectTakeoffSettings.project_id == project.id).first()
        if takeoff is None:
            takeoff = ProjectTakeoffSettings(project_id=project.id)
        takeoff.m2_basis = "PAINTABLE_TOTAL"
        db.add(takeoff)
    db.commit()
    return project.id, desired_hourly, target_margin


def render_case_snapshot(db: Session, case_name: str) -> dict:
    db.query(BufferRule).delete()
    db.commit()
    _configure_defaults(db)
    started = time.perf_counter()
    project_id, desired_hourly, target_margin = _populate_case(db, case_name)
    baseline, scenarios = compute_pricing_scenarios(db, project_id)
    conversions = compute_conversions(
        db,
        project_id,
        DesiredInput(desired_effective_hourly_ex_vat=desired_hourly, desired_margin_pct=target_margin),
    )
    policy = db.query(PricingPolicy).first() or get_or_create_pricing_policy(db)
    floor_by_mode = {scenario.mode: evaluate_floor(baseline, scenario, policy) for scenario in scenarios}
    elapsed_s = Decimal(str(time.perf_counter() - started)).quantize(Decimal("0.0001"))

    payload = {
        "case": case_name,
        "baseline": {
            "labor_hours_total": baseline.labor_hours_total,
            "labor_cost_internal": baseline.labor_cost_internal,
            "materials_cost_internal": baseline.materials_cost_internal,
            "travel_setup_cost_internal": baseline.travel_setup_cost_internal,
            "overhead_cost_internal": baseline.overhead_cost_internal,
            "internal_total_cost": baseline.internal_total_cost,
            "total_m2": baseline.total_m2,
            "rooms_count": baseline.rooms_count,
            "items_count": baseline.items_count,
        },
        "scenarios": {
            s.mode: {
                "price_ex_vat": s.price_ex_vat,
                "effective_hourly": s.effective_hourly_sell_rate,
                "profit": s.profit,
                "margin_pct": s.margin_pct,
                "warnings": s.warnings,
                "invalid": s.invalid,
            }
            for s in scenarios
        },
        "converter": {
            "input": {
                "desired_effective_hourly_ex_vat": desired_hourly,
                "desired_margin_pct": target_margin,
            },
            "base_price_ex_vat": conversions.base_price_ex_vat,
            "implied_fixed_total_price": conversions.implied_fixed_total_price,
            "implied_rate_per_m2": conversions.implied_rate_per_m2,
            "implied_rate_per_room": conversions.implied_rate_per_room,
            "implied_rate_per_piece": conversions.implied_rate_per_piece,
            "effective_hourly_ex_vat": conversions.effective_hourly_ex_vat,
            "profit": conversions.profit,
            "margin_pct": conversions.margin_pct,
            "warnings": conversions.warnings,
            "mode_results": {
                mode: {
                    "price_ex_vat": estimate.price_ex_vat,
                    "effective_hourly": estimate.effective_hourly_ex_vat,
                    "profit": estimate.profit,
                    "margin_pct": estimate.margin_pct,
                    "warnings": estimate.warnings,
                }
                for mode, estimate in conversions.mode_results.items()
            },
        },
        "floor": {
            mode: {
                "is_below_floor": result.is_below_floor,
                "reasons": [reason.code for reason in result.reasons],
                "recommended_min_price_ex_vat": result.recommended_min_price_ex_vat,
                "recommended_rate_per_m2": result.recommended_rate_per_m2,
                "recommended_rate_per_room": result.recommended_rate_per_room,
                "recommended_rate_per_piece": result.recommended_rate_per_piece,
                "recommended_fixed_total": result.recommended_fixed_total,
            }
            for mode, result in floor_by_mode.items()
        },
        "performance": {
            "compute_seconds": elapsed_s,
        },
    }
    return _norm(payload)


def load_golden(case_name: str) -> dict:
    with (GOLDEN_DIR / f"{case_name}.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def write_golden(case_name: str, payload: dict) -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    with (GOLDEN_DIR / f"{case_name}.json").open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
