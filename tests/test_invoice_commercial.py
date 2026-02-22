from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Invoice, Project, ProjectPricing, ProjectTakeoffSettings, Room
from app.models.pricing_policy import get_or_create_pricing_policy
from app.services.invoice_lines import generate_invoice_lines_from_project, recalculate_invoice_totals

client = TestClient(app)
settings = get_settings()


def _login():
    client.post('/login', data={'username': settings.admin_email, 'password': settings.admin_password}, follow_redirects=False)


def _mk_project(mode: str, *, fixed=0, per_m2=0, per_room=0, basis='FLOOR_AREA') -> tuple[int, int]:
    db = SessionLocal()
    try:
        p = Project(name=f'InvCommercial-{mode}')
        db.add(p)
        db.flush()
        db.add_all([
            Room(project_id=p.id, name='R1', floor_area_m2=Decimal('10'), wall_perimeter_m=Decimal('10'), wall_height_m=Decimal('4'), wall_area_m2=Decimal('40'), ceiling_area_m2=Decimal('10')),
            Room(project_id=p.id, name='R2', floor_area_m2=Decimal('20'), wall_perimeter_m=Decimal('15'), wall_height_m=Decimal('4'), wall_area_m2=Decimal('60'), ceiling_area_m2=Decimal('20')),
        ])
        db.add(ProjectTakeoffSettings(project_id=p.id, m2_basis=basis))
        db.add(ProjectPricing(project_id=p.id, mode=mode, fixed_total_price=Decimal(str(fixed)), rate_per_m2=Decimal(str(per_m2)), rate_per_room=Decimal(str(per_room))))
        policy = get_or_create_pricing_policy(db)
        policy.warn_only_mode = True
        db.add(policy)
        db.flush()
        inv = Invoice(project_id=p.id, issue_date=date.today(), status='draft', work_sum_without_moms=0, moms_amount=0, rot_amount=0, client_pays_total=0)
        db.add(inv)
        db.commit()
        return p.id, inv.id
    finally:
        db.close()


def test_invoice_line_generation_matches_mode_totals():
    for mode, val, expected_qty in [('FIXED_TOTAL', Decimal('5000.00'), Decimal('1.00')), ('PER_M2', Decimal('100.00'), Decimal('30.00')), ('PER_ROOM', Decimal('2000.00'), Decimal('2.00'))]:
        kwargs = {'fixed': val} if mode == 'FIXED_TOTAL' else {'per_m2': val} if mode == 'PER_M2' else {'per_room': val}
        pid, iid = _mk_project(mode, **kwargs)
        db = SessionLocal()
        try:
            generate_invoice_lines_from_project(db, project_id=pid, invoice_id=iid, include_labor=True, include_materials=False)
            recalculate_invoice_totals(db, iid)
            inv = db.get(Invoice, iid)
            assert len(inv.lines) == 1
            assert inv.lines[0].quantity == expected_qty
            assert inv.subtotal_ex_vat == (val * expected_qty).quantize(Decimal('0.01'))
            db.rollback()
        finally:
            db.close()


def test_invoice_per_m2_uses_takeoff_basis():
    pid, iid = _mk_project('PER_M2', per_m2=Decimal('50.00'), basis='WALL_AREA')
    db = SessionLocal()
    try:
        generate_invoice_lines_from_project(db, project_id=pid, invoice_id=iid, include_labor=True, include_materials=False)
        inv = db.get(Invoice, iid)
        assert 'väggyta' in inv.lines[0].description
        assert inv.lines[0].quantity == Decimal('100.00')
        db.rollback()
    finally:
        db.close()


def test_create_invoice_from_project_generates_correct_lines_for_mode():
    _login()
    pid, _ = _mk_project('PER_ROOM', per_room=Decimal('1234.00'))
    resp = client.post(f'/projects/{pid}/invoices/create-from-project', data={'include_labor': 'true', 'merge_strategy': 'REPLACE_ALL'}, follow_redirects=False)
    assert resp.status_code == 303
    db = SessionLocal()
    try:
        inv = db.query(Invoice).filter(Invoice.project_id == pid).order_by(Invoice.id.desc()).first()
        assert inv.lines[0].unit == 'rum'
        assert inv.lines[0].unit_price_ex_vat == Decimal('1234.00')
    finally:
        db.close()


def test_invoice_finalize_blocks_on_totals_mismatch():
    _login()
    pid, iid = _mk_project('FIXED_TOTAL', fixed=Decimal('1000.00'))
    db = SessionLocal()
    try:
        generate_invoice_lines_from_project(db, project_id=pid, invoice_id=iid)
        inv = db.get(Invoice, iid)
        inv.lines[0].unit_price_ex_vat = Decimal('999.00')
        db.commit()
    finally:
        db.close()

    resp = client.post(f'/invoices/{iid}/finalize', headers={'accept': 'application/json'}, follow_redirects=False)
    assert resp.status_code == 409
    assert resp.json()['detail'] == 'Invoice totals mismatch pricing scenario'


def test_invoice_issued_snapshot_immutable():
    _login()
    pid, iid = _mk_project('FIXED_TOTAL', fixed=Decimal('1500.00'))
    db = SessionLocal()
    try:
        generate_invoice_lines_from_project(db, project_id=pid, invoice_id=iid)
        db.commit()
    finally:
        db.close()

    r = client.post(f'/invoices/{iid}/finalize', follow_redirects=False)
    assert r.status_code == 303

    db = SessionLocal()
    try:
        inv = db.get(Invoice, iid)
        snap = inv.subtotal_ex_vat_snapshot
        pricing = db.query(ProjectPricing).filter(ProjectPricing.project_id == pid).first()
        pricing.fixed_total_price = Decimal('9999.00')
        db.add(pricing)
        db.flush()
        recalculate_invoice_totals(db, iid)
        db.refresh(inv)
        assert inv.subtotal_ex_vat_snapshot == snap
    finally:
        db.rollback()
        db.close()
