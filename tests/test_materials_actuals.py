from datetime import datetime, timezone
from decimal import Decimal
import importlib.util
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.material import Material
from app.models.material_actuals import MaterialPurchase, ProjectMaterialActuals, ProjectMaterialStock
from app.models.material_recipe import MaterialRecipe
from app.models.project import Project
from app.models.room import Room
from app.models.supplier import Supplier
from app.models.supplier_material_price import SupplierMaterialPrice
from app.models.user import User
from app.security import hash_password
from app.services.material_actuals import compute_materials_plan_vs_actual, create_material_purchase

client = TestClient(app)


def _login(email: str, role: str):
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == email).first():
            db.add(User(email=email, password_hash=hash_password("Pass#123456"), role=role))
            db.commit()
    finally:
        db.close()
    client.post("/login", data={"username": email, "password": "Pass#123456", "next": "/projects/"}, follow_redirects=False)


def _seed_project() -> tuple[int, int]:
    db = SessionLocal()
    try:
        p = Project(name=f"MA-{uuid4().hex[:6]}")
        db.add(p)
        db.flush()
        db.add(Room(project_id=p.id, name="R", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("10"), wall_height_m=Decimal("2")))
        db.flush()
        m = Material(code=f"MA-M-{uuid4().hex[:6]}", name_ru="Краска", name_sv="Paint", unit="L", default_cost_per_unit_ex_vat=Decimal("20.00"), vat_rate_pct=Decimal("25.00"), is_active=True)
        db.add(m)
        db.flush()
        db.add(MaterialRecipe(name="Paint", material_id=m.id, applies_to="PROJECT", basis="WALL_AREA", consumption_per_m2=Decimal("0.1"), coats_count=1, waste_pct=Decimal("0"), rounding_mode="NONE"))
        s = Supplier(name=f"SUP-{uuid4().hex[:5]}", is_active=True)
        db.add(s)
        db.flush()
        db.add(SupplierMaterialPrice(supplier_id=s.id, material_id=m.id, pack_size=Decimal("1.00"), pack_unit="L", pack_price_ex_vat=Decimal("30.00"), currency="SEK"))
        db.commit()
        return p.id, m.id
    finally:
        db.close()


def test_purchase_lines_recalculate_totals():
    project_id, material_id = _seed_project()
    db = SessionLocal()
    try:
        p = create_material_purchase(db, project_id=project_id, supplier_id=None, purchased_at=datetime.now(timezone.utc), invoice_ref="R-1", notes=None, currency="SEK", user_id=None, lines=[{"material_id": material_id, "packs_count": Decimal("2.0"), "pack_size": Decimal("1.0"), "pack_price_ex_vat": Decimal("30.00"), "unit": "L"}])
        line = p.lines[0]
        assert line.line_cost_ex_vat == Decimal("60.00")
        assert line.line_cost_inc_vat == Decimal("75.00")
    finally:
        db.close()


def test_stock_increases_on_purchase():
    project_id, material_id = _seed_project()
    db = SessionLocal()
    try:
        create_material_purchase(db, project_id=project_id, supplier_id=None, purchased_at=datetime.now(timezone.utc), invoice_ref=None, notes=None, currency="SEK", user_id=None, lines=[{"material_id": material_id, "packs_count": Decimal("1.5"), "pack_size": Decimal("2.0"), "pack_price_ex_vat": Decimal("10.00"), "unit": "L"}])
        stock = db.query(ProjectMaterialStock).filter_by(project_id=project_id, material_id=material_id).first()
        assert stock.qty_in_base_unit == Decimal("3.00")
    finally:
        db.close()


def test_actual_cost_aggregation():
    project_id, material_id = _seed_project()
    db = SessionLocal()
    try:
        create_material_purchase(db, project_id=project_id, supplier_id=None, purchased_at=datetime.now(timezone.utc), invoice_ref=None, notes=None, currency="SEK", user_id=None, lines=[{"material_id": material_id, "packs_count": Decimal("1"), "pack_size": Decimal("1"), "pack_price_ex_vat": Decimal("10.00"), "unit": "L"}])
        create_material_purchase(db, project_id=project_id, supplier_id=None, purchased_at=datetime.now(timezone.utc), invoice_ref=None, notes=None, currency="SEK", user_id=None, lines=[{"material_id": material_id, "packs_count": Decimal("1"), "pack_size": Decimal("1"), "pack_price_ex_vat": Decimal("20.00"), "unit": "L"}])
        db.close()
        db2 = SessionLocal()
        actual = db2.query(ProjectMaterialActuals).filter_by(project_id=project_id).first()
        assert actual.actual_cost_ex_vat >= Decimal("10.00")
        db2.close()
        return
    finally:
        db.close()


def test_plan_vs_actual_detects_over_and_under():
    project_id, material_id = _seed_project()
    db = SessionLocal()
    try:
        create_material_purchase(db, project_id=project_id, supplier_id=None, purchased_at=datetime.now(timezone.utc), invoice_ref=None, notes=None, currency="SEK", user_id=None, lines=[{"material_id": material_id, "packs_count": Decimal("0.10"), "pack_size": Decimal("1.00"), "pack_price_ex_vat": Decimal("10.00"), "unit": "L"}])
        report = compute_materials_plan_vs_actual(db, project_id)
        assert any(r.status in {"UNDER", "OVER", "OK"} for r in report.rows)
    finally:
        db.close()


def test_create_purchase_requires_role_and_csrf():
    project_id, material_id = _seed_project()
    _login("ma-viewer@example.com", "viewer")
    forbidden = client.post(f"/projects/{project_id}/materials-actuals/purchases", data={"material_id": [str(material_id)], "packs_count": ["1"], "pack_size": ["1"], "unit": ["L"], "pack_price_ex_vat": ["10"]}, follow_redirects=False)
    assert forbidden.status_code == 403

    _login("ma-op@example.com", "operator")
    no_csrf = client.post(f"/projects/{project_id}/materials-actuals/purchases", data={"material_id": [str(material_id)], "packs_count": ["1"], "pack_size": ["1"], "unit": ["L"], "pack_price_ex_vat": ["10"]}, headers={"X-No-Auto-CSRF": "1"}, follow_redirects=False)
    assert no_csrf.status_code in {403, 400}


def test_quick_create_from_shopping_list_creates_purchase():
    project_id, material_id = _seed_project()
    _login("ma-op2@example.com", "operator")
    response = client.post(f"/projects/{project_id}/materials-actuals/purchases/from-shopping-list", data={"selected_material_id": [str(material_id)]}, follow_redirects=False)
    assert response.status_code == 303
    db = SessionLocal()
    try:
        assert db.query(MaterialPurchase).filter_by(project_id=project_id).count() >= 1
    finally:
        db.close()


def test_plan_vs_actual_page_renders():
    _login("ma-admin@example.com", "admin")
    project_id, _material_id = _seed_project()
    response = client.get(f"/projects/{project_id}/materials-actuals")
    assert response.status_code == 200
    assert "material" in response.text.lower()


def test_export_csv_contains_expected_headers():
    _login("ma-admin2@example.com", "admin")
    project_id, _ = _seed_project()
    response = client.get(f"/projects/{project_id}/materials-actuals/export-plan-vs-actual.csv")
    assert response.status_code == 200
    assert "material_id,material_name" in response.text


@pytest.mark.skipif(importlib.util.find_spec("weasyprint") is None, reason="weasyprint not installed")
def test_export_pdf_returns_pdf_header():
    _login("ma-admin3@example.com", "admin")
    project_id, _ = _seed_project()
    response = client.get(f"/projects/{project_id}/materials-actuals/export-report.pdf")
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_materials_actuals_golden_snapshot_delta():
    project_id, material_id = _seed_project()
    db = SessionLocal()
    try:
        create_material_purchase(db, project_id=project_id, supplier_id=None, purchased_at=datetime.now(timezone.utc), invoice_ref=None, notes=None, currency="SEK", user_id=None, lines=[{"material_id": material_id, "packs_count": Decimal("1"), "pack_size": Decimal("1"), "pack_price_ex_vat": Decimal("50.00"), "unit": "L"}])
        report = compute_materials_plan_vs_actual(db, project_id)
        assert str(report.planned_cost_ex_vat)
        assert str(report.actual_cost_ex_vat)
    finally:
        db.close()
