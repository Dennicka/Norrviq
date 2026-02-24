from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.material_catalog_item import MaterialCatalogItem
from app.models.material_norm import MaterialConsumptionNorm
from app.models.project import Project
from app.models.room import Room
from app.models.user import User
from app.models.worktype import WorkType
from app.models.project import ProjectWorkItem
from app.security import hash_password
from app.services.material_costing import cost_material_rows, cost_project_materials
from app.services.materials_consumption import MaterialNeedTotal

client = TestClient(app)


def _login():
    db = SessionLocal()
    try:
        email = f"mc-{uuid4().hex[:6]}@example.com"
        db.add(User(email=email, password_hash=hash_password("Pass#123456"), role="admin"))
        db.commit()
    finally:
        db.close()
    client.post("/login", data={"username": email, "password": "Pass#123456", "next": "/projects/"}, follow_redirects=False)


def test_catalog_crud_create_test():
    _login()
    resp = client.post("/materials/catalog/new", data={"material_code": "paint_white", "name": "Paint 10L", "unit": "l", "package_size": "10", "package_unit": "l", "price_ex_vat": "500", "vat_rate_pct": "25", "supplier_name": "Acme", "is_active": "on"}, follow_redirects=False)
    assert resp.status_code == 303
    db = SessionLocal()
    try:
        assert db.query(MaterialCatalogItem).filter_by(material_code="paint_white").first() is not None
    finally:
        db.close()


def test_package_rounding_test():
    db = SessionLocal()
    try:
        db.add(MaterialCatalogItem(material_code="paint_white", name="Paint", unit="l", package_size=Decimal("10"), package_unit="l", price_ex_vat=Decimal("500"), vat_rate_pct=Decimal("25"), is_active=True, is_default_for_material=True))
        db.commit()
        rows = cost_material_rows(db, [MaterialNeedTotal(material_name="Paint White", material_unit="l", total_quantity=Decimal("12"))])
        assert rows[0].packages_to_buy == 2
        assert rows[0].purchasable_quantity == Decimal("20.0000")
        assert rows[0].overbuy_quantity == Decimal("8.0000")
    finally:
        db.close()


def test_default_product_selection_test():
    code = f"paint_white_{uuid4().hex[:6]}"
    db = SessionLocal()
    try:
        db.add(MaterialCatalogItem(material_code=code, name="A", unit="l", package_size=Decimal("10"), package_unit="l", price_ex_vat=Decimal("600"), vat_rate_pct=Decimal("25"), is_active=True, is_default_for_material=False))
        db.add(MaterialCatalogItem(material_code=code, name="B", unit="l", package_size=Decimal("10"), package_unit="l", price_ex_vat=Decimal("700"), vat_rate_pct=Decimal("25"), is_active=True, is_default_for_material=True))
        db.commit()
        rows = cost_material_rows(db, [MaterialNeedTotal(material_name=code.replace("_", " "), material_unit="l", total_quantity=Decimal("2"))])
        selected = db.get(MaterialCatalogItem, rows[0].selected_catalog_item_id)
        assert selected.name == "B"
    finally:
        db.close()


def test_cheapest_per_unit_fallback_test():
    code = f"primer_{uuid4().hex[:6]}"
    db = SessionLocal()
    try:
        db.add(MaterialCatalogItem(material_code=code, name="A", unit="l", package_size=Decimal("3"), package_unit="l", price_ex_vat=Decimal("300"), vat_rate_pct=Decimal("25"), is_active=True, is_default_for_material=False))
        db.add(MaterialCatalogItem(material_code=code, name="B", unit="l", package_size=Decimal("10"), package_unit="l", price_ex_vat=Decimal("800"), vat_rate_pct=Decimal("25"), is_active=True, is_default_for_material=False))
        db.commit()
        rows = cost_material_rows(db, [MaterialNeedTotal(material_name=code.replace("_", " "), material_unit="l", total_quantity=Decimal("9"))])
        selected = db.get(MaterialCatalogItem, rows[0].selected_catalog_item_id)
        assert selected.name == "B"
    finally:
        db.close()


def test_unit_mismatch_test():
    db = SessionLocal()
    try:
        db.add(MaterialCatalogItem(material_code="putty", name="P", unit="kg", package_size=Decimal("10"), package_unit="kg", price_ex_vat=Decimal("100"), vat_rate_pct=Decimal("25"), is_active=True, is_default_for_material=True))
        db.commit()
        rows = cost_material_rows(db, [MaterialNeedTotal(material_name="Putty", material_unit="l", total_quantity=Decimal("1"))])
        assert "UNIT_MISMATCH" in rows[0].warnings
    finally:
        db.close()


def _seed_project_with_material() -> int:
    db = SessionLocal()
    try:
        p = Project(name=f"P-{uuid4().hex[:6]}")
        wt = WorkType(code=f"paint-{uuid4().hex[:4]}", name_ru="Покраска стен", name_sv="Painting walls", unit="m2", hours_per_unit=Decimal("1"), is_active=True)
        db.add_all([p, wt])
        db.flush()
        db.add(Room(project_id=p.id, name="R1", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("12"), wall_height_m=Decimal("2.5"), wall_area_m2=Decimal("30")))
        db.flush()
        db.add(ProjectWorkItem(project_id=p.id, work_type_id=wt.id, quantity=Decimal("1"), room_id=None))
        db.add(MaterialConsumptionNorm(material_name="Paint White", material_category="paint", applies_to_work_type="painting_walls", work_kind="painting_walls", basis_type="wall_area", quantity_per_basis=Decimal("0.2"), basis_unit="m2", material_unit="l", waste_factor_pct=Decimal("0"), surface_type="wall", consumption_value=Decimal("0.2"), waste_percent=Decimal("0"), coats_multiplier_mode="none", active=True, is_active=True))
        db.add(MaterialCatalogItem(material_code="paint_white", name="Paint 10L", unit="l", package_size=Decimal("10"), package_unit="l", price_ex_vat=Decimal("500"), vat_rate_pct=Decimal("25"), is_active=True, is_default_for_material=True))
        db.commit()
        return p.id
    finally:
        db.close()


def test_project_totals_integration_test():
    project_id = _seed_project_with_material()
    db = SessionLocal()
    try:
        report = cost_project_materials(db, project_id)
        assert report.total_ex_vat > 0
    finally:
        db.close()


def test_unresolved_materials_ui_test():
    _login()
    project_id = _seed_project_with_material()
    db = SessionLocal()
    try:
        db.query(MaterialCatalogItem).delete()
        db.commit()
    finally:
        db.close()
    response = client.get(f"/projects/{project_id}/shopping-list")
    assert response.status_code == 200
    assert "Unresolved materials" in response.text


def test_invalid_catalog_input_test():
    _login()
    resp = client.post("/materials/catalog/new", data={"material_code": "x", "name": "x", "unit": "l", "package_size": "-1", "package_unit": "l", "price_ex_vat": "-5", "vat_rate_pct": "120"})
    assert resp.status_code == 422
