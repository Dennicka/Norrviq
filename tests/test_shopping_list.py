from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.invoice import Invoice
from app.models.material import Material
from app.models.material_recipe import MaterialRecipe
from app.models.project import Project
from app.models.project_procurement_settings import ProjectProcurementSettings
from app.models.room import Room
from app.models.supplier import Supplier
from app.models.supplier_material_price import SupplierMaterialPrice
from app.models.user import User
from app.security import hash_password
from app.services.shopping_list import compute_project_shopping_list

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


def _seed_project(consumption_per_m2: str = "0.1", area_m2: str = "10") -> tuple[int, int]:
    db = SessionLocal()
    try:
        p = Project(name=f"S-{uuid4().hex[:6]}")
        db.add(p)
        db.flush()
        db.add(Room(project_id=p.id, name="R", floor_area_m2=Decimal(area_m2), wall_perimeter_m=Decimal("10"), wall_height_m=Decimal("2")))
        db.flush()
        m = Material(code=f"M-{uuid4().hex[:6]}", name_ru="Краска", name_sv="Paint", unit="L", default_cost_per_unit_ex_vat=Decimal("20.00"), vat_rate_pct=Decimal("25.00"), is_active=True)
        db.add(m)
        db.flush()
        db.add(MaterialRecipe(name="Paint", material_id=m.id, applies_to="PROJECT", basis="WALL_AREA", consumption_per_m2=Decimal(consumption_per_m2), coats_count=1, waste_pct=Decimal("0"), rounding_mode="NONE"))
        db.commit()
        return p.id, m.id
    finally:
        db.close()


def _configure_material(material_id: int, *, pack_size: str | None, rule: str = "CEIL", min_pack_qty: str = "1"):
    db = SessionLocal()
    try:
        material = db.get(Material, material_id)
        if pack_size is None:
            material.pack_size = None
            material.pack_unit = None
        else:
            material.pack_size = Decimal(pack_size)
            material.pack_unit = "L"
        material.pack_rounding_rule = rule
        material.min_pack_qty = Decimal(min_pack_qty)
        db.add(material)
        db.commit()
    finally:
        db.close()


def _add_supplier_price(material_id: int, *, supplier: str, pack_size: str, pack_price: str):
    db = SessionLocal()
    try:
        s = Supplier(name=f"{supplier}-{uuid4().hex[:4]}", is_active=True)
        db.add(s)
        db.flush()
        db.add(SupplierMaterialPrice(supplier_id=s.id, material_id=material_id, pack_size=Decimal(pack_size), pack_unit="L", pack_price_ex_vat=Decimal(pack_price), currency="SEK"))
        db.commit()
        return s.id
    finally:
        db.close()


def test_rounding_ceil_12_1_to_10_is_2_packs():
    project_id, material_id = _seed_project(consumption_per_m2="0.605")
    _configure_material(material_id, pack_size="10", rule="CEIL")
    _add_supplier_price(material_id, supplier="A", pack_size="10", pack_price="100")
    db = SessionLocal()
    try:
        report = compute_project_shopping_list(db, project_id)
        row = next(i for i in report.items if i.material_id == material_id)
        assert row.planned_qty == Decimal("12.1000")
        assert row.packs_needed == Decimal("2")
    finally:
        db.close()


def test_rounding_exact_20kg_to_20_is_1_pack():
    project_id, material_id = _seed_project(consumption_per_m2="1")
    _configure_material(material_id, pack_size="20", rule="CEIL")
    _add_supplier_price(material_id, supplier="A", pack_size="20", pack_price="200")
    db = SessionLocal()
    try:
        report = compute_project_shopping_list(db, project_id)
        row = next(i for i in report.items if i.material_id == material_id)
        assert row.planned_qty == Decimal("20.0000")
        assert row.packs_needed == Decimal("1")
    finally:
        db.close()


def test_zero_qty_excluded():
    project_id, material_id = _seed_project(consumption_per_m2="0")
    _configure_material(material_id, pack_size="10")
    _add_supplier_price(material_id, supplier="A", pack_size="10", pack_price="100")
    db = SessionLocal()
    try:
        report = compute_project_shopping_list(db, project_id)
        assert all(i.material_id != material_id for i in report.items)
    finally:
        db.close()


def test_missing_pack_size_adds_warning_deterministic():
    project_id, material_id = _seed_project(consumption_per_m2="0.1")
    _configure_material(material_id, pack_size=None)
    _add_supplier_price(material_id, supplier="A", pack_size="0.00", pack_price="100")
    db = SessionLocal()
    try:
        report1 = compute_project_shopping_list(db, project_id)
        report2 = compute_project_shopping_list(db, project_id)
        assert any("NO_PACK_SIZE" in w for w in report1.warnings)
        assert report1.source_hash == report2.source_hash
    finally:
        db.close()


def test_integration_cheapest_supplier_and_total_cost():
    project_id, material_id = _seed_project(consumption_per_m2="0.605")
    _configure_material(material_id, pack_size="10", rule="CEIL")
    _add_supplier_price(material_id, supplier="A", pack_size="10", pack_price="100")
    _add_supplier_price(material_id, supplier="B", pack_size="10", pack_price="80")
    db = SessionLocal()
    try:
        settings = db.query(ProjectProcurementSettings).filter_by(project_id=project_id).first() or ProjectProcurementSettings(project_id=project_id)
        settings.auto_select_cheapest = True
        db.add(settings)
        db.commit()
        report = compute_project_shopping_list(db, project_id)
        row = next(i for i in report.items if i.material_id == material_id)
        assert row.unit_price == Decimal("80")
        assert row.line_total_cost == Decimal("160.00")
    finally:
        db.close()


def test_shopping_list_page_renders():
    _login("shop-admin@example.com", "admin")
    project_id, _ = _seed_project()
    response = client.get(f"/projects/{project_id}/shopping-list")
    assert response.status_code == 200
    assert 'data-testid="shopping-title"' in response.text


def test_export_csv_downloads():
    _login("shop-admin2@example.com", "admin")
    project_id, _ = _seed_project()
    response = client.get(f"/projects/{project_id}/shopping-list/export.csv")
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/csv")


def test_export_pdf_or_fallback_returns_200():
    _login("shop-admin3@example.com", "admin")
    project_id, _ = _seed_project()
    response = client.get(f"/projects/{project_id}/shopping-list/export.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] in {"application/pdf", "text/html; charset=utf-8"}


def test_apply_to_costs_idempotent():
    _login("shop-op@example.com", "operator")
    project_id, _ = _seed_project()
    first = client.post(f"/projects/{project_id}/shopping-list/apply-costs", follow_redirects=False)
    second = client.post(f"/projects/{project_id}/shopping-list/apply-costs", follow_redirects=False)
    assert first.status_code == 303
    assert second.status_code == 409


def test_apply_to_invoice_adds_material_lines():
    _login("shop-op2@example.com", "operator")
    project_id, _ = _seed_project()
    db = SessionLocal()
    try:
        inv = Invoice(project_id=project_id, status="draft", issue_date=date(2026, 1, 1), work_sum_without_moms=Decimal("0"), moms_amount=Decimal("0"), rot_amount=Decimal("0"), client_pays_total=Decimal("0"), subtotal_ex_vat=Decimal("0"), vat_total=Decimal("0"), total_inc_vat=Decimal("0"))
        db.add(inv)
        db.commit()
    finally:
        db.close()
    response = client.post(f"/projects/{project_id}/shopping-list/apply-invoice", follow_redirects=False)
    assert response.status_code == 303


def test_shopping_list_print_renders():
    _login("shop-admin4@example.com", "admin")
    project_id, _ = _seed_project()
    response = client.get(f"/projects/{project_id}/shopping-list/print")
    assert response.status_code == 200
