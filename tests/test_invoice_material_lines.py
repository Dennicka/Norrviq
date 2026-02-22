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
from app.models.project_pricing import ProjectPricing
from app.models.project_procurement_settings import ProjectProcurementSettings
from app.models.room import Room
from app.models.supplier import Supplier
from app.models.supplier_material_price import SupplierMaterialPrice
from app.models.user import User
from app.security import hash_password
from app.services.invoice_material_lines import add_material_lines

client = TestClient(app)


def _login(email: str = "materials-admin@example.com"):
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == email).first():
            db.add(User(email=email, password_hash=hash_password("Pass#123456"), role="admin"))
            db.commit()
    finally:
        db.close()
    client.post("/login", data={"username": email, "password": "Pass#123456", "next": "/projects/"}, follow_redirects=False)


def _seed() -> tuple[int, int]:
    db = SessionLocal()
    try:
        p = Project(name=f"M-{uuid4().hex[:6]}")
        db.add(p)
        db.flush()
        db.add(ProjectPricing(project_id=p.id, mode="FIXED_TOTAL", fixed_total_price=Decimal("100.00"), include_materials=True))
        db.add(Room(project_id=p.id, name="R", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("10"), wall_height_m=Decimal("2")))
        m = Material(code=f"MAT-{uuid4().hex[:6]}", name_ru="Краска", name_sv="Paint", unit="L", sku="SKU1", default_pack_size=Decimal("10"), default_cost_per_unit_ex_vat=Decimal("20"), default_sell_per_unit_ex_vat=Decimal("25"), vat_rate_pct=Decimal("25"), is_active=True)
        db.add(m)
        db.flush()
        db.add(MaterialRecipe(name="Paint", material_id=m.id, applies_to="PROJECT", basis="WALL_AREA", consumption_per_m2=Decimal("0.2"), coats_count=1, waste_pct=Decimal("0"), rounding_mode="NONE"))
        s = Supplier(name=f"S-{uuid4().hex[:4]}", is_active=True)
        db.add(s)
        db.flush()
        db.add(SupplierMaterialPrice(supplier_id=s.id, material_id=m.id, pack_size=Decimal("10"), pack_unit="L", pack_price_ex_vat=Decimal("100"), currency="SEK"))
        inv = Invoice(project_id=p.id, status="draft", issue_date=date(2026, 1, 1), work_sum_without_moms=0, moms_amount=0, rot_amount=0, client_pays_total=0, subtotal_ex_vat=0, vat_total=0, total_inc_vat=0)
        db.add(inv)
        db.commit()
        return p.id, inv.id
    finally:
        db.close()


def test_material_line_pricing_cost_plus_markup():
    pid, iid = _seed()
    db = SessionLocal()
    try:
        settings = ProjectProcurementSettings(project_id=pid, material_pricing_mode="COST_PLUS_MARKUP", material_markup_pct=Decimal("20"), invoice_material_unit="PACKS", round_invoice_materials_to_packs=True)
        db.add(settings)
        db.commit()
        add_material_lines(db, project_id=pid, invoice_id=iid, source="SHOPPING_LIST", merge_strategy="REPLACE_MATERIALS", pricing_mode_override=None, user_id=None)
        db.commit()
        inv = db.get(Invoice, iid)
        assert inv.lines[0].unit_price_ex_vat == Decimal("120.00")
    finally:
        db.close()


def test_material_line_pricing_sell_price():
    pid, iid = _seed()
    db = SessionLocal()
    try:
        settings = ProjectProcurementSettings(project_id=pid, material_pricing_mode="SELL_PRICE", invoice_material_unit="PACKS")
        db.add(settings)
        db.commit()
        add_material_lines(db, project_id=pid, invoice_id=iid, source="SHOPPING_LIST", merge_strategy="REPLACE_MATERIALS", pricing_mode_override=None, user_id=None)
        db.commit()
        inv = db.get(Invoice, iid)
        assert inv.lines[0].unit_price_ex_vat == Decimal("100.00")
    finally:
        db.close()


def test_pack_vs_base_unit_generation():
    pid, iid = _seed()
    db = SessionLocal()
    try:
        settings = ProjectProcurementSettings(project_id=pid, material_pricing_mode="SELL_PRICE", invoice_material_unit="BASE_UNIT")
        db.add(settings)
        db.commit()
        add_material_lines(db, project_id=pid, invoice_id=iid, source="SHOPPING_LIST", merge_strategy="REPLACE_MATERIALS", pricing_mode_override=None, user_id=None)
        db.commit()
        inv = db.get(Invoice, iid)
        assert inv.lines[0].unit == "L"
        assert inv.lines[0].unit_price_ex_vat == Decimal("10.00")
    finally:
        db.close()


def test_add_material_lines_from_shopping_list():
    _login()
    pid, iid = _seed()
    response = client.post(f"/projects/{pid}/invoices/{iid}/add-material-lines", data={"source": "SHOPPING_LIST", "merge_strategy": "REPLACE_MATERIALS"}, follow_redirects=False)
    assert response.status_code == 303


def test_finalize_blocks_if_materials_present_but_pricing_excludes_materials():
    _login("materials-admin2@example.com")
    pid, iid = _seed()
    db = SessionLocal()
    try:
        pricing = db.query(ProjectPricing).filter(ProjectPricing.project_id == pid).first()
        pricing.include_materials = False
        db.add(pricing)
        db.commit()
    finally:
        db.close()
    client.post(f"/projects/{pid}/invoices/{iid}/add-material-lines", data={"source": "SHOPPING_LIST", "merge_strategy": "REPLACE_MATERIALS"}, follow_redirects=False)
    resp = client.post(f"/invoices/{iid}/finalize", headers={"accept": "application/json"}, follow_redirects=False)
    assert resp.status_code == 409


def test_material_lines_immutable_when_issued():
    _login("materials-admin3@example.com")
    pid, iid = _seed()
    client.post(f"/projects/{pid}/invoices/{iid}/add-material-lines", data={"source": "SHOPPING_LIST", "merge_strategy": "REPLACE_MATERIALS"}, follow_redirects=False)
    issue = client.post(f"/invoices/{iid}/finalize", follow_redirects=False)
    assert issue.status_code in (302, 303)
    db = SessionLocal()
    try:
        inv = db.get(Invoice, iid)
        inv.status = "issued"
        db.add(inv)
        db.commit()
    finally:
        db.close()
    locked = client.post(f"/projects/{pid}/invoices/{iid}/add-material-lines", data={"source": "SHOPPING_LIST", "merge_strategy": "REPLACE_MATERIALS"}, follow_redirects=False)
    assert locked.status_code == 409
