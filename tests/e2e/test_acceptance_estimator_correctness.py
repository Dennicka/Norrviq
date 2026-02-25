from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.material import Material
from app.models.material_consumption_override import MaterialConsumptionOverride
from app.models.material_norm import MaterialConsumptionNorm
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.estimator_workspace import build_estimator_workspace
from app.services.materials_bom import compute_project_bom
from app.services.pricing import get_or_create_project_pricing

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "golden" / "acceptance_estimator_correctness.json"


def _d2(value: Decimal | int | float | None) -> str:
    return str(Decimal(str(value or 0)).quantize(Decimal("0.01")))


def _login(client: TestClient) -> None:
    settings = get_settings()
    response = client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password}, follow_redirects=False)
    assert response.status_code in (302, 303)


def _create_project(client: TestClient, label: str) -> int:
    c = client.post("/clients/new", data={"name": f"Acceptance {label} {uuid4().hex[:6]}"}, follow_redirects=False)
    assert c.status_code == 303
    client_id = int(c.headers["location"].split("/")[-1])
    p = client.post(
        "/projects/new",
        data={"name": f"Acceptance Project {label} {uuid4().hex[:6]}", "client_id": str(client_id), "status": "draft"},
        follow_redirects=False,
    )
    assert p.status_code == 303
    return int(p.headers["location"].split("/")[-1])


def _create_room(client: TestClient, project_id: int, name: str, *, length: str, width: str, height: str, openings: str = "0") -> None:
    response = client.post(
        f"/projects/{project_id}/rooms/create",
        data={"name": name, "length_m": length, "width_m": width, "wall_height_m": height, "openings_area_m2": openings},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _create_work_type_and_norm(db, *, suffix: str, category: str, unit: str, hours_per_unit: str, material_price: str, consumption_value: str, surface: str = "custom") -> tuple[int, int, int]:
    wt = WorkType(
        code=f"ACC-{suffix}-{uuid4().hex[:4]}",
        category=category,
        unit=unit,
        name_ru=f"{suffix} RU",
        name_sv=f"{suffix} SV",
        hours_per_unit=Decimal(hours_per_unit),
        is_active=True,
    )
    material = Material(
        code=f"ACC-MAT-{suffix}-{uuid4().hex[:4]}",
        name_ru=f"MAT {suffix} RU",
        name_sv=f"MAT {suffix} SV",
        unit="l",
        default_price_per_unit=Decimal(material_price),
        is_active=True,
    )
    norm = MaterialConsumptionNorm(
        applies_to_work_type=wt.code,
        work_type_code=wt.code,
        material_name=material.name_sv,
        material_category="consumable",
        material_unit="l",
        consumption_value=Decimal(consumption_value),
        consumption_unit="per_1_m2",
        surface_type=surface,
        active=True,
        is_active=True,
        waste_percent=Decimal("0"),
    )
    db.add_all([wt, material, norm])
    db.commit()
    return wt.id, material.id, norm.id


def _set_pricing(project_id: int, *, hourly: str, fixed: str, per_m2: str) -> None:
    db = SessionLocal()
    try:
        pricing = get_or_create_project_pricing(db, project_id)
        pricing.mode = "HOURLY"
        pricing.hourly_rate_override = Decimal(hourly)
        pricing.fixed_total_price = Decimal(fixed)
        pricing.rate_per_m2 = Decimal(per_m2)
        pricing.rate_per_room = Decimal("2400")
        pricing.rate_per_piece = Decimal("800")
        pricing.target_margin_pct = Decimal("30")
        pricing.include_materials = True
        db.add(pricing)
        db.commit()
    finally:
        db.close()


def _collect_snapshot(client: TestClient, project_id: int, *, invalid_check: dict | None = None) -> dict:
    db = SessionLocal()
    try:
        workspace = build_estimator_workspace(db, project_id, lang="en")
        bom = compute_project_bom(db, project_id)
    finally:
        db.close()

    pricing_json = client.get(f"/projects/{project_id}/pricing", headers={"accept": "application/json"})
    assert pricing_json.status_code == 200
    pricing_data = pricing_json.json()
    compare_rows = {
        row["mode"]: {
            "price_ex_vat": _d2(row["price_ex_vat"]),
            "margin_pct": _d2(row["margin_pct"]),
            "effective_hourly_sell_rate": _d2(row["effective_hourly_sell_rate"]),
            "invalid": bool(row["invalid"]),
        }
        for row in pricing_data["scenarios"]
    }

    client.post(f"/projects/{project_id}/workflow/create-offer-draft", data={}, follow_redirects=False)
    create_invoice = client.post(
        f"/projects/{project_id}/invoices/create-from-project",
        data={"include_labor": "true", "merge_strategy": "REPLACE_ALL"},
        follow_redirects=False,
    )
    assert create_invoice.status_code in (302, 303)
    invoice_id = int(create_invoice.headers["location"].split("/")[-1])

    offer_preview = client.get(f"/projects/{project_id}/offer")
    offer_pdf = client.get(f"/offers/{project_id}/pdf")
    invoice_pdf = client.get(f"/invoices/{invoice_id}/pdf")
    invoice_print = client.get(f"/invoices/{invoice_id}/print")

    assert offer_preview.status_code == 200
    assert offer_pdf.status_code == 200
    assert invoice_pdf.status_code == 200
    assert invoice_print.status_code == 200

    snapshot = {
        "total_hours": _d2(workspace["totals"]["total_hours"]),
        "money": {
            "ex_vat": _d2(workspace["totals"]["subtotal"]),
            "vat": _d2(workspace["totals"]["vat"]),
            "total": _d2(workspace["totals"]["total"]),
        },
        "pricing_compare": compare_rows,
        "materials_plan": {
            "total_cost_ex_vat": _d2(bom.total_cost_ex_vat),
            "lines": len(bom.items),
        },
        "documents": {
            "offer_preview": offer_preview.status_code,
            "offer_pdf": offer_pdf.status_code,
            "invoice_pdf": invoice_pdf.status_code,
            "invoice_print": invoice_print.status_code,
        },
    }
    if invalid_check is not None:
        snapshot["invalid_check"] = invalid_check
    return snapshot


def test_acceptance_estimator_correctness_real_life_golden() -> None:
    expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    with TestClient(app) as client:
        _login(client)

        # 1) 1 room repaint (walls+ceiling, 2 coats, basic prep)
        project_1 = _create_project(client, "s1")
        _create_room(client, project_1, "Living", length="4", width="3", height="2.5")
        db = SessionLocal()
        try:
            wall_id, _, _ = _create_work_type_and_norm(db, suffix="S1-WALL", category="wall", unit="m2", hours_per_unit="0.08", material_price="120", consumption_value="0.12", surface="wall")
            ceil_id, _, _ = _create_work_type_and_norm(db, suffix="S1-CEIL", category="ceiling", unit="m2", hours_per_unit="0.06", material_price="95", consumption_value="0.10", surface="ceiling")
            prep_id, _, _ = _create_work_type_and_norm(db, suffix="S1-PREP", category="wall", unit="m2", hours_per_unit="0.04", material_price="35", consumption_value="0.05", surface="wall")
            room = db.query(Room).filter(Room.project_id == project_1).first()
            assert room is not None
            room_id_1 = room.id
            wall_area = _d2(room.wall_area_m2)
            ceil_area = _d2(room.ceiling_area_m2)
        finally:
            db.close()
        _set_pricing(project_1, hourly="760", fixed="9800", per_m2="220")
        client.post(f"/projects/{project_1}/add-work-item", data={"work_type_id": str(wall_id), "room_id": str(room_id_1), "quantity": wall_area, "layers": "2", "difficulty_factor": "1.0"}, follow_redirects=False)
        client.post(f"/projects/{project_1}/add-work-item", data={"work_type_id": str(ceil_id), "room_id": str(room_id_1), "quantity": ceil_area, "layers": "2", "difficulty_factor": "1.0"}, follow_redirects=False)
        client.post(f"/projects/{project_1}/add-work-item", data={"work_type_id": str(prep_id), "room_id": str(room_id_1), "quantity": wall_area, "layers": "1", "difficulty_factor": "1.0"}, follow_redirects=False)
        s1 = _collect_snapshot(client, project_1)

        # 2) Apartment (3 rooms) bulk apply floor protection + ceiling paint for all rooms
        project_2 = _create_project(client, "s2")
        _create_room(client, project_2, "R1", length="4", width="3", height="2.5")
        _create_room(client, project_2, "R2", length="5", width="3", height="2.5")
        _create_room(client, project_2, "R3", length="3", width="3", height="2.5")
        db = SessionLocal()
        try:
            floor_id, _, _ = _create_work_type_and_norm(db, suffix="S2-FLOOR", category="floor", unit="m2", hours_per_unit="0.03", material_price="18", consumption_value="1.00", surface="floor")
            ceil_id_2, _, _ = _create_work_type_and_norm(db, suffix="S2-CEIL", category="ceiling", unit="m2", hours_per_unit="0.06", material_price="98", consumption_value="0.11", surface="ceiling")
        finally:
            db.close()
        _set_pricing(project_2, hourly="720", fixed="15000", per_m2="190")
        client.post(f"/projects/{project_2}/add-work-item", data={"work_type_id": str(floor_id), "scope_mode": "all_rooms", "layers": "1", "difficulty_factor": "1.0"}, follow_redirects=False)
        client.post(f"/projects/{project_2}/add-work-item", data={"work_type_id": str(ceil_id_2), "scope_mode": "all_rooms", "layers": "1", "difficulty_factor": "1.0"}, follow_redirects=False)
        s2 = _collect_snapshot(client, project_2)

        # 3) Apartment with 2 windows+1 door per room (openings impact)
        project_3 = _create_project(client, "s3")
        _create_room(client, project_3, "R1", length="4", width="3", height="2.5", openings="4.8")
        _create_room(client, project_3, "R2", length="4", width="3", height="2.5", openings="4.8")
        _create_room(client, project_3, "R3", length="4", width="3", height="2.5", openings="4.8")
        db = SessionLocal()
        try:
            wall_id_3, _, _ = _create_work_type_and_norm(db, suffix="S3-WALL", category="wall", unit="m2", hours_per_unit="0.08", material_price="120", consumption_value="0.12", surface="wall")
        finally:
            db.close()
        _set_pricing(project_3, hourly="760", fixed="17000", per_m2="210")
        client.post(f"/projects/{project_3}/add-work-item", data={"work_type_id": str(wall_id_3), "scope_mode": "all_rooms", "layers": "1", "difficulty_factor": "1.0"}, follow_redirects=False)
        s3 = _collect_snapshot(client, project_3)

        # 4) Fastpris vs hourly compare (margin + effective hourly)
        project_4 = _create_project(client, "s4")
        _create_room(client, project_4, "Office", length="7", width="4", height="2.7")
        db = SessionLocal()
        try:
            wall_id_4, _, _ = _create_work_type_and_norm(db, suffix="S4-WALL", category="wall", unit="m2", hours_per_unit="0.11", material_price="130", consumption_value="0.16", surface="wall")
            room = db.query(Room).filter(Room.project_id == project_4).first()
            assert room is not None
            room_id_4 = room.id
            wall_area_4 = _d2(room.wall_area_m2)
        finally:
            db.close()
        _set_pricing(project_4, hourly="690", fixed="21000", per_m2="260")
        client.post(f"/projects/{project_4}/add-work-item", data={"work_type_id": str(wall_id_4), "quantity": wall_area_4, "room_id": str(room_id_4), "layers": "2", "difficulty_factor": "1.1"}, follow_redirects=False)
        s4 = _collect_snapshot(client, project_4)

        # 5) Materials plan with overrides (custom norms > defaults)
        project_5 = _create_project(client, "s5")
        _create_room(client, project_5, "Kitchen", length="4", width="4", height="2.5")
        db = SessionLocal()
        try:
            wall_id_5, material_id_5, _ = _create_work_type_and_norm(db, suffix="S5-WALL", category="wall", unit="m2", hours_per_unit="0.09", material_price="120", consumption_value="0.10", surface="wall")
            room = db.query(Room).filter(Room.project_id == project_5).first()
            assert room is not None
            room_id_5 = room.id
            wall_area_5 = _d2(room.wall_area_m2)
        finally:
            db.close()
        _set_pricing(project_5, hourly="740", fixed="14000", per_m2="230")
        client.post(f"/projects/{project_5}/add-work-item", data={"work_type_id": str(wall_id_5), "quantity": wall_area_5, "room_id": str(room_id_5), "layers": "1", "difficulty_factor": "1.0"}, follow_redirects=False)
        db = SessionLocal()
        try:
            override = MaterialConsumptionOverride(
                project_id=project_5,
                room_id=None,
                work_type_id=wall_id_5,
                material_id=material_id_5,
                surface_kind="wall",
                unit_basis="m2",
                quantity_per_unit=Decimal("0.25"),
                base_unit_size=Decimal("1.0"),
                waste_factor_percent=Decimal("0"),
                comment="Acceptance override",
                is_active=True,
            )
            db.add(override)
            db.commit()
        finally:
            db.close()
        s5 = _collect_snapshot(client, project_5)

        # 6) Sanity checks (invalid inputs blocked with clear reason)
        project_6 = _create_project(client, "s6")
        _create_room(client, project_6, "R1", length="4", width="3", height="2.5")
        _set_pricing(project_6, hourly="700", fixed="9000", per_m2="180")
        invalid_work_type = client.post(f"/projects/{project_6}/add-work-item", data={"quantity": "10"}, follow_redirects=False)
        assert invalid_work_type.status_code == 400
        assert invalid_work_type.json()["detail"] == "Work type required"
        invalid_project = client.get("/projects/9999999/pricing", headers={"accept": "application/json"})
        assert invalid_project.status_code == 404
        assert invalid_project.json()["detail"] == "Project not found"
        s6 = _collect_snapshot(
            client,
            project_6,
            invalid_check={
                "missing_work_type": {"status": invalid_work_type.status_code, "detail": invalid_work_type.json()["detail"]},
                "missing_project": {"status": invalid_project.status_code, "detail": invalid_project.json()["detail"]},
            },
        )

    actual = {
        "scenario_1": s1,
        "scenario_2": s2,
        "scenario_3": s3,
        "scenario_4": s4,
        "scenario_5": s5,
        "scenario_6": s6,
    }
    assert actual == expected
