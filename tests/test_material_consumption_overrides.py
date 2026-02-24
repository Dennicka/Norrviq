from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.material import Material
from app.models.material_consumption_override import MaterialConsumptionOverride
from app.models.material_norm import MaterialConsumptionNorm
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.materials_bom import compute_project_bom, resolve_material_norm

client = TestClient(app)
settings = get_settings()


def login():
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def _seed(surface_type: str = "ceiling"):
    db = SessionLocal()
    p = Project(name=f"OVR-{uuid4().hex[:6]}")
    wt = WorkType(code=f"wt_{uuid4().hex[:4]}", category="ceiling", unit="m2", name_ru="", name_sv="", description_ru=None, description_sv=None, hours_per_unit=Decimal("1"), base_difficulty_factor=Decimal("1"), is_active=True)
    m = Material(code=f"mat_{uuid4().hex[:4]}", name_ru="Краска", name_sv="Ceiling paint", unit="l", is_active=True)
    db.add_all([p, wt, m])
    db.flush()
    r1 = Room(project_id=p.id, name="R1", floor_area_m2=Decimal("10"), wall_area_m2=Decimal("20"), ceiling_area_m2=Decimal("10"))
    r2 = Room(project_id=p.id, name="R2", floor_area_m2=Decimal("7"), wall_area_m2=Decimal("15"), ceiling_area_m2=Decimal("7"))
    db.add_all([r1, r2])
    db.flush()
    db.add(ProjectWorkItem(project_id=p.id, room_id=r1.id, work_type_id=wt.id, quantity=Decimal("1"), difficulty_factor=Decimal("1")))
    norm = MaterialConsumptionNorm(active=True, material_name="Ceiling paint", material_category="paint", applies_to_work_type=wt.code, surface_type=surface_type, consumption_value=Decimal("1"), consumption_unit="per_10_m2", material_unit="l", waste_percent=Decimal("0"), coats_multiplier_mode="none", default_unit_price_sek=Decimal("10"))
    db.add(norm)
    db.commit()
    return p.id, wt.id, m.id, r1.id, r2.id, norm.id


def test_resolver_priority_room_over_project_over_default():
    project_id, work_type_id, material_id, room_id, _, norm_id = _seed()
    db = SessionLocal()
    try:
        norm = db.get(MaterialConsumptionNorm, norm_id)
        db.add(MaterialConsumptionOverride(project_id=project_id, room_id=None, work_type_id=work_type_id, material_id=material_id, surface_kind="ceiling", unit_basis="m2", quantity_per_unit=Decimal("2"), base_unit_size=Decimal("10"), is_active=True))
        db.add(MaterialConsumptionOverride(project_id=project_id, room_id=room_id, work_type_id=work_type_id, material_id=material_id, surface_kind="ceiling", unit_basis="m2", quantity_per_unit=Decimal("3"), base_unit_size=Decimal("10"), is_active=True))
        db.commit()
        resolved = resolve_material_norm(db, project_id, room_id, work_type_id, material_id, "ceiling", norm)
        assert resolved.quantity_per_unit == Decimal("3")

        resolved_project = resolve_material_norm(db, project_id, None, work_type_id, material_id, "ceiling", norm)
        assert resolved_project.quantity_per_unit == Decimal("2")

        resolved_default = resolve_material_norm(db, project_id, room_id, work_type_id, None, "ceiling", norm)
        assert resolved_default.quantity_per_unit == Decimal("1")
    finally:
        db.close()


def test_surface_and_project_sum_and_missing_geometry_warning():
    project_id, work_type_id, material_id, room_id, room2_id, _ = _seed(surface_type="walls")
    db = SessionLocal()
    try:
        db.add(MaterialConsumptionOverride(project_id=project_id, room_id=room_id, work_type_id=work_type_id, material_id=material_id, surface_kind="walls", unit_basis="m2", quantity_per_unit=Decimal("1"), base_unit_size=Decimal("10"), is_active=True))
        db.commit()
        bom = compute_project_bom(db, project_id)
        assert bom.items[0].area_m2_used == Decimal("20.0000")
    finally:
        db.close()

    project_id2, work_type_id2, material_id2, _room_id2, room2_id2, _ = _seed(surface_type="ceiling")
    db2 = SessionLocal()
    try:
        wi = db2.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id2).first()
        wi.room_id = None
        db2.add(wi)
        db2.add(MaterialConsumptionOverride(project_id=project_id2, room_id=None, work_type_id=work_type_id2, material_id=material_id2, surface_kind="ceiling", unit_basis="m2", quantity_per_unit=Decimal("3"), base_unit_size=Decimal("10"), is_active=True))
        bad_room = db2.get(Room, room2_id2)
        bad_room.ceiling_area_m2 = None
        db2.add(bad_room)
        db2.commit()

        bom2 = compute_project_bom(db2, project_id2)
        assert bom2.items[0].area_m2_used == Decimal("10.0000")
        assert any("MISSING_GEOMETRY:ceiling" in w for w in bom2.warnings)
    finally:
        db2.close()


def test_override_crud_and_duplicate_blocked_and_bom_changed():
    login()
    project_id, work_type_id, material_id, room_id, _, _ = _seed()

    before = SessionLocal()
    try:
        original_qty = compute_project_bom(before, project_id).items[0].qty_final_unit
    finally:
        before.close()

    create_resp = client.post(f"/projects/{project_id}/materials/overrides", data={"room_id": str(room_id), "work_type_id": str(work_type_id), "material_id": str(material_id), "surface_kind": "ceiling", "unit_basis": "m2", "quantity_per_unit": "3", "base_unit_size": "10", "waste_factor_percent": "0", "is_active": "on", "comment": "3L/10m2"}, follow_redirects=False)
    assert create_resp.status_code == 303

    db = SessionLocal()
    try:
        row = db.query(MaterialConsumptionOverride).filter(MaterialConsumptionOverride.project_id == project_id).first()
        assert row is not None
        edit_resp = client.post(f"/projects/{project_id}/materials/overrides/{row.id}/edit", data={"surface_kind": "ceiling", "unit_basis": "m2", "quantity_per_unit": "4", "base_unit_size": "10", "waste_factor_percent": "0", "is_active": "on", "comment": "upd"}, follow_redirects=False)
        assert edit_resp.status_code == 303
    finally:
        db.close()

    dup_resp = client.post(f"/projects/{project_id}/materials/overrides", data={"room_id": str(room_id), "work_type_id": str(work_type_id), "material_id": str(material_id), "surface_kind": "ceiling", "unit_basis": "m2", "quantity_per_unit": "4", "base_unit_size": "10", "is_active": "on"}, follow_redirects=True)
    assert dup_resp.status_code == 200
    assert "duplicate" in dup_resp.text.lower() or "существ" in dup_resp.text.lower()

    after = SessionLocal()
    try:
        changed_qty = compute_project_bom(after, project_id).items[0].qty_final_unit
        assert changed_qty != original_qty
    finally:
        after.close()


def test_no_override_regression_same_bom():
    project_id, _, _, _, _, _ = _seed()
    db = SessionLocal()
    try:
        first = compute_project_bom(db, project_id).total_cost_ex_vat
        second = compute_project_bom(db, project_id).total_cost_ex_vat
        assert first == second
    finally:
        db.close()
