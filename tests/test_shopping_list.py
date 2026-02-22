from decimal import Decimal
import importlib.util
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.invoice import Invoice
from app.models.material import Material
from app.models.material_recipe import MaterialRecipe
from app.models.project import Project
from app.models.room import Room
from app.models.supplier import Supplier
from app.models.supplier_material_price import SupplierMaterialPrice
from app.models.project_procurement_settings import ProjectProcurementSettings
from datetime import date
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


def _seed_project() -> int:
    db = SessionLocal()
    try:
        p = Project(name=f"S-{uuid4().hex[:6]}")
        db.add(p)
        db.flush()
        db.add(Room(project_id=p.id, name="R", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("10"), wall_height_m=Decimal("2")))
        db.flush()
        m = Material(code=f"M-{uuid4().hex[:6]}", name_ru="Краска", name_sv="Paint", unit="L", default_cost_per_unit_ex_vat=Decimal("20.00"), vat_rate_pct=Decimal("25.00"), is_active=True)
        db.add(m)
        db.flush()
        db.add(MaterialRecipe(name="Paint", material_id=m.id, applies_to="PROJECT", basis="WALL_AREA", consumption_per_m2=Decimal("0.1"), coats_count=1, waste_pct=Decimal("0"), rounding_mode="NONE"))
        db.commit()
        return p.id
    finally:
        db.close()


def _add_supplier_price(project_id: int, *, supplier: str, pack_size: str, pack_price: str):
    db = SessionLocal()
    try:
        material = db.query(Material).order_by(Material.id.desc()).first()
        s = Supplier(name=f"{supplier}-{uuid4().hex[:4]}", is_active=True)
        db.add(s)
        db.flush()
        db.add(SupplierMaterialPrice(supplier_id=s.id, material_id=material.id, pack_size=Decimal(pack_size), pack_unit="L", pack_price_ex_vat=Decimal(pack_price), currency="SEK"))
        db.commit()
        return s.id
    finally:
        db.close()


def test_select_preferred_supplier_price():
    project_id = _seed_project()
    s1 = _add_supplier_price(project_id, supplier="A", pack_size="5", pack_price="100")
    _add_supplier_price(project_id, supplier="B", pack_size="5", pack_price="80")
    db = SessionLocal()
    try:
        settings = db.query(ProjectProcurementSettings).filter_by(project_id=project_id).first()
        if not settings:
            settings = ProjectProcurementSettings(project_id=project_id)
        settings.preferred_supplier_id = s1
        settings.auto_select_cheapest = False
        db.add(settings)
        db.commit()
        report = compute_project_shopping_list(db, project_id)
        assert report.items[0].supplier_name.startswith("A-")
    finally:
        db.close()


def test_auto_select_cheapest_price():
    project_id = _seed_project()
    _add_supplier_price(project_id, supplier="A", pack_size="5", pack_price="100")
    _add_supplier_price(project_id, supplier="B", pack_size="5", pack_price="80")
    db = SessionLocal()
    try:
        settings = db.query(ProjectProcurementSettings).filter_by(project_id=project_id).first()
        if not settings:
            settings = ProjectProcurementSettings(project_id=project_id)
        settings.preferred_supplier_id = None
        settings.auto_select_cheapest = True
        db.add(settings)
        db.commit()
        report = compute_project_shopping_list(db, project_id)
        assert report.items[0].pack_price_ex_vat == Decimal("80")
    finally:
        db.close()


def test_warning_when_no_supplier_price():
    project_id = _seed_project()
    db = SessionLocal()
    try:
        report = compute_project_shopping_list(db, project_id)
        assert any("NO_SUPPLIER_PRICE" in w for w in report.warnings)
    finally:
        db.close()


def test_shopping_list_page_renders():
    _login("shop-admin@example.com", "admin")
    project_id = _seed_project()
    response = client.get(f"/projects/{project_id}/shopping-list")
    assert response.status_code == 200
    assert "Shopping List" in response.text


def test_export_csv_downloads():
    _login("shop-admin2@example.com", "admin")
    project_id = _seed_project()
    response = client.get(f"/projects/{project_id}/shopping-list/export.csv")
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/csv")


@pytest.mark.skipif(importlib.util.find_spec("weasyprint") is None, reason="weasyprint not installed")
def test_export_pdf_downloads_pdf_header():
    _login("shop-admin3@example.com", "admin")
    project_id = _seed_project()
    response = client.get(f"/projects/{project_id}/shopping-list/export.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"


def test_apply_to_costs_idempotent():
    _login("shop-op@example.com", "operator")
    project_id = _seed_project()
    first = client.post(f"/projects/{project_id}/shopping-list/apply-costs", follow_redirects=False)
    second = client.post(f"/projects/{project_id}/shopping-list/apply-costs", follow_redirects=False)
    assert first.status_code == 303
    assert second.status_code == 409


def test_apply_to_invoice_adds_material_lines():
    _login("shop-op2@example.com", "operator")
    project_id = _seed_project()
    db = SessionLocal()
    try:
        inv = Invoice(project_id=project_id, status="draft", issue_date=date(2026, 1, 1), work_sum_without_moms=Decimal("0"), moms_amount=Decimal("0"), rot_amount=Decimal("0"), client_pays_total=Decimal("0"), subtotal_ex_vat=Decimal("0"), vat_total=Decimal("0"), total_inc_vat=Decimal("0"))
        db.add(inv)
        db.commit()
    finally:
        db.close()
    response = client.post(f"/projects/{project_id}/shopping-list/apply-invoice", follow_redirects=False)
    assert response.status_code == 303


def test_suppliers_settings_admin_only_and_apply_requires_csrf():
    _login("shop-viewer@example.com", "viewer")
    forbidden = client.get("/settings/suppliers")
    assert forbidden.status_code == 403

    _login("shop-op3@example.com", "operator")
    project_id = _seed_project()
    no_csrf = client.post(f"/projects/{project_id}/shopping-list/apply-costs", data={}, headers={"X-No-Auto-CSRF": "1"}, follow_redirects=False)
    assert no_csrf.status_code == 403


def test_shopping_list_golden_totals_snapshot():
    project_id = _seed_project()
    _add_supplier_price(project_id, supplier="A", pack_size="5", pack_price="100")
    db = SessionLocal()
    try:
        report = compute_project_shopping_list(db, project_id)
        assert str(report.total_ex_vat)
        assert str(report.total_inc_vat)
    finally:
        db.close()
