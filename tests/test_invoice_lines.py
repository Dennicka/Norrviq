from datetime import date
from decimal import Decimal
import re

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Invoice, InvoiceLine, Project, ProjectPricing, ProjectWorkItem, Room, RotCase, User, WorkType
from app.security import hash_password
from app.services.invoice_lines import (
    MERGE_APPEND,
    MERGE_REPLACE_ALL,
    MERGE_UPSERT_BY_SOURCE,
    recalculate_invoice_totals,
)

client = TestClient(app)
settings = get_settings()
CSRF_META_RE = re.compile(r'<meta\s+name="csrf-token"\s+content="([^"]+)"')


def _csrf(html: str) -> str:
    return CSRF_META_RE.search(html).group(1)


def _login(email=None, password=None):
    login_page = client.get("/login")
    token = _csrf(login_page.text)
    client.post("/login", data={"username": email or settings.admin_email, "password": password or settings.admin_password, "csrf_token": token}, headers={"X-CSRF-Token": token})


def _create_project_with_work() -> int:
    db = SessionLocal()
    try:
        p = Project(name="InvoiceLines Project")
        db.add(p)
        db.flush()
        room = Room(project_id=p.id, name="Kitchen")
        wt = WorkType(code=f"W-{p.id}", unit="m2", name_ru="Шпаклевка", name_sv="Spackling", hours_per_unit=Decimal("2.0"), base_difficulty_factor=Decimal("1.0"))
        db.add_all([room, wt])
        db.flush()
        db.add(ProjectPricing(project_id=p.id, mode="HOURLY", hourly_rate_override=Decimal("500")))
        db.add(ProjectWorkItem(project_id=p.id, room_id=room.id, work_type_id=wt.id, quantity=Decimal("10"), calculated_hours=Decimal("8"), calculated_cost_without_moms=Decimal("4000"), difficulty_factor=Decimal("1")))
        db.commit()
        return p.id
    finally:
        db.close()


def _create_invoice(project_id: int) -> int:
    page = client.get(f"/projects/{project_id}/invoices/create")
    token = _csrf(page.text)
    client.post(f"/projects/{project_id}/invoices/create", data={"issue_date": date.today().isoformat(), "work_sum_without_moms": "100.00", "moms_amount": "25.00", "rot_amount": "0", "client_pays_total": "125.00", "csrf_token": token}, headers={"X-CSRF-Token": token})
    db = SessionLocal()
    try:
        inv = db.query(Invoice).filter(Invoice.project_id == project_id).order_by(Invoice.id.desc()).first()
        return inv.id
    finally:
        db.close()


def test_generate_lines_replace_all_creates_expected_count():
    _login()
    pid = _create_project_with_work()
    iid = _create_invoice(pid)
    page = client.get(f"/projects/{pid}/invoices/{iid}/edit")
    token = _csrf(page.text)
    r = client.post(f"/projects/{pid}/invoices/{iid}/generate-lines", data={"include_labor": "true", "merge_strategy": MERGE_REPLACE_ALL, "csrf_token": token}, headers={"X-CSRF-Token": token}, follow_redirects=False)
    assert r.status_code == 303
    db = SessionLocal()
    try:
        inv = db.get(Invoice, iid)
        assert len(inv.lines) == 1
    finally:
        db.close()


def test_recalculate_totals_matches_sum_of_lines():
    _login()
    pid = _create_project_with_work()
    iid = _create_invoice(pid)
    db = SessionLocal()
    try:
        recalculate_invoice_totals(db, iid)
        inv = db.get(Invoice, iid)
        summed = sum((Decimal(str(line.line_total_ex_vat or 0)) for line in inv.lines), Decimal("0"))
        assert inv.subtotal_ex_vat == summed.quantize(Decimal("0.01"))
    finally:
        db.rollback()
        db.close()


def test_invoice_edit_blocks_when_issued():
    _login()
    pid = _create_project_with_work()
    iid = _create_invoice(pid)
    db = SessionLocal()
    try:
        inv = db.get(Invoice, iid)
        inv.status = "issued"
        db.commit()
    finally:
        db.close()
    edit = client.get(f"/projects/{pid}/invoices/{iid}/edit")
    token = _csrf(edit.text)
    resp = client.post(f"/projects/{pid}/invoices/{iid}/generate-lines", data={"csrf_token": token}, headers={"X-CSRF-Token": token})
    assert resp.status_code == 409


def test_generate_lines_respects_merge_strategy():
    _login()
    pid = _create_project_with_work()
    iid = _create_invoice(pid)
    page = client.get(f"/projects/{pid}/invoices/{iid}/edit")
    token = _csrf(page.text)
    client.post(f"/projects/{pid}/invoices/{iid}/generate-lines", data={"merge_strategy": MERGE_APPEND, "csrf_token": token}, headers={"X-CSRF-Token": token})
    db = SessionLocal()
    try:
        inv = db.get(Invoice, iid)
        assert len(inv.lines) >= 2
    finally:
        db.close()
    page = client.get(f"/projects/{pid}/invoices/{iid}/edit")
    token = _csrf(page.text)
    client.post(f"/projects/{pid}/invoices/{iid}/generate-lines", data={"merge_strategy": MERGE_UPSERT_BY_SOURCE, "csrf_token": token}, headers={"X-CSRF-Token": token})


def test_invoice_lines_decimal_rounding():
    _login()
    pid = _create_project_with_work()
    iid = _create_invoice(pid)
    page = client.get(f"/projects/{pid}/invoices/{iid}/edit")
    token = _csrf(page.text)
    db = SessionLocal()
    try:
        line_id = db.get(Invoice, iid).lines[0].id
    finally:
        db.close()
    client.patch(f"/projects/{pid}/invoices/{iid}/lines/{line_id}", json={"description": "x", "quantity": "1.235", "unit_price_ex_vat": "10.005", "unit": "h", "vat_rate_pct": "25"}, headers={"X-CSRF-Token": token})
    db = SessionLocal()
    try:
        inv = db.get(Invoice, iid)
        assert inv.lines[0].line_total_ex_vat == Decimal("12.41")
    finally:
        db.close()


def test_rbac_and_csrf_for_invoice_lines():
    _login()
    pid = _create_project_with_work()
    iid = _create_invoice(pid)

    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == "viewer-lines@example.com").first():
            db.add(User(email="viewer-lines@example.com", password_hash=hash_password("pw"), role="viewer"))
            db.commit()
    finally:
        db.close()
    _login("viewer-lines@example.com", "pw")
    page = client.get(f"/projects/{pid}/invoices/{iid}/edit")
    token = _csrf(page.text)
    forbidden = client.post(f"/projects/{pid}/invoices/{iid}/lines/add", data={"csrf_token": token}, headers={"X-CSRF-Token": token})
    assert forbidden.status_code == 403
    _login()
    no_csrf = client.post(f"/projects/{pid}/invoices/{iid}/lines/add", data={}, headers={"X-No-Auto-CSRF": "1"})
    assert no_csrf.status_code == 403


def test_labor_material_split_totals():
    _login()
    pid = _create_project_with_work()
    iid = _create_invoice(pid)
    db = SessionLocal()
    try:
        invoice = db.get(Invoice, iid)
        first = invoice.lines[0]
        first.kind = "LABOR"
        first.quantity = Decimal("2")
        first.unit_price_ex_vat = Decimal("100")
        db.add(
            InvoiceLine(
                invoice_id=iid,
                position=2,
                kind="MATERIAL",
                description="Paint",
                quantity=Decimal("1"),
                unit_price_ex_vat=Decimal("40"),
                vat_rate_pct=Decimal("25"),
                source_type="MANUAL",
            )
        )
        db.commit()
        recalculate_invoice_totals(db, iid)
        invoice = db.get(Invoice, iid)
        assert invoice.labour_ex_vat == Decimal("200.00")
        assert invoice.material_ex_vat == Decimal("40.00")
        assert invoice.other_ex_vat == Decimal("0.00")
    finally:
        db.rollback()
        db.close()


def test_rot_applies_only_to_labor_ex_vat():
    _login()
    pid = _create_project_with_work()
    iid = _create_invoice(pid)
    db = SessionLocal()
    try:
        invoice = db.get(Invoice, iid)
        line = invoice.lines[0]
        line.kind = "LABOR"
        line.quantity = Decimal("1")
        line.unit_price_ex_vat = Decimal("100")
        db.add(
            InvoiceLine(
                invoice_id=iid,
                position=2,
                kind="MATERIAL",
                description="Material",
                quantity=Decimal("1"),
                unit_price_ex_vat=Decimal("200"),
                vat_rate_pct=Decimal("25"),
                source_type="MANUAL",
            )
        )
        db.add(RotCase(invoice_id=iid, is_enabled=True, rot_pct=Decimal("30")))
        db.flush()
        recalculate_invoice_totals(db, iid)
        assert invoice.rot_amount == Decimal("30.00")
    finally:
        db.rollback()
        db.close()


def test_rot_clamped_not_below_zero():
    _login()
    pid = _create_project_with_work()
    iid = _create_invoice(pid)
    db = SessionLocal()
    try:
        invoice = db.get(Invoice, iid)
        line = invoice.lines[0]
        line.kind = "LABOR"
        line.quantity = Decimal("1")
        line.unit_price_ex_vat = Decimal("1")
        line.vat_rate_pct = Decimal("0")
        db.add(RotCase(invoice_id=iid, is_enabled=True, rot_pct=Decimal("200")))
        db.flush()
        recalculate_invoice_totals(db, iid)
        assert invoice.client_pays_total == Decimal("0.00")
    finally:
        db.rollback()
        db.close()
