from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import CommercialSnapshot, Invoice, Project, ProjectPricing, ProjectTakeoffSettings, Room
from app.models.pricing_policy import get_or_create_pricing_policy
from app.services.commercial_snapshot import DOC_TYPE_INVOICE, write_commercial_snapshot
from app.services.invoice_commercial import compute_invoice_commercial
from app.services.invoice_lines import generate_invoice_lines_from_project, recalculate_invoice_totals
from app.services.pricing_consistency import validate_pricing_consistency

client = TestClient(app)
settings = get_settings()


def _login():
    client.post('/login', data={'username': settings.admin_email, 'password': settings.admin_password}, follow_redirects=False)


def _mk(mode='FIXED_TOTAL', value=Decimal('1000.00')):
    db = SessionLocal()
    try:
        p = Project(name='Consistency')
        db.add(p)
        db.flush()
        db.add(Room(project_id=p.id, name='R1', floor_area_m2=Decimal('10'), wall_perimeter_m=Decimal('10'), wall_height_m=Decimal('3'), wall_area_m2=Decimal('30'), ceiling_area_m2=Decimal('10')))
        db.add(ProjectTakeoffSettings(project_id=p.id, m2_basis='PAINTABLE_TOTAL'))
        kwargs = {'fixed_total_price': value} if mode == 'FIXED_TOTAL' else {'rate_per_m2': value}
        db.add(ProjectPricing(project_id=p.id, mode=mode, **kwargs))
        policy = get_or_create_pricing_policy(db)
        policy.warn_only_mode = True
        db.add(policy)
        inv = Invoice(project_id=p.id, issue_date=date.today(), status='draft', work_sum_without_moms=0, moms_amount=0, rot_amount=0, client_pays_total=0)
        db.add(inv)
        db.commit()
        return p.id, inv.id
    finally:
        db.close()


def test_validate_pricing_consistency_detects_mismatch():
    pid, iid = _mk()
    db = SessionLocal()
    try:
        generate_invoice_lines_from_project(db, project_id=pid, invoice_id=iid)
        inv = db.get(Invoice, iid)
        inv.lines[0].unit_price_ex_vat = Decimal('777.00')
        recalculate_invoice_totals(db, iid)
        db.commit()

        result = validate_pricing_consistency(db, pid, 'INVOICE', iid)
        assert not result.ok
        assert any(err['code'] == 'INVOICE_SUBTOTAL_MISMATCH' for err in result.errors)
    finally:
        db.close()


def test_snapshot_written_on_issue_and_immutable():
    pid, iid = _mk()
    db = SessionLocal()
    try:
        commercial = compute_invoice_commercial(db, pid, iid)
        snap_id = write_commercial_snapshot(db, DOC_TYPE_INVOICE, iid, commercial)
        db.commit()
        assert snap_id

        inv = db.get(Invoice, iid)
        inv.status = 'issued'
        db.commit()

        same_id = write_commercial_snapshot(db, DOC_TYPE_INVOICE, iid, commercial)
        assert same_id == snap_id
        assert db.query(CommercialSnapshot).filter(CommercialSnapshot.doc_type == 'INVOICE', CommercialSnapshot.doc_id == iid).count() == 1
    finally:
        db.rollback()
        db.close()


def test_offer_issue_blocks_if_pricing_rate_changed_after_offer_draft():
    _login()
    pid, _ = _mk(mode='PER_M2', value=Decimal('100.00'))

    first_draft = client.get(f'/projects/{pid}/offer?lang=sv')
    assert first_draft.status_code == 200

    db = SessionLocal()
    try:
        pricing = db.query(ProjectPricing).filter(ProjectPricing.project_id == pid).first()
        pricing.rate_per_m2 = Decimal('150.00')
        room = db.query(Room).filter(Room.project_id == pid).first()
        room.floor_area_m2 = Decimal('0.00')
        db.add_all([pricing, room])
        db.commit()
    finally:
        db.close()

    resp = client.post(f'/offers/{pid}/finalize', headers={'accept': 'application/json'}, follow_redirects=False)
    assert resp.status_code == 409


def test_invoice_issue_blocks_if_invoice_lines_manually_edited_to_mismatch():
    _login()
    pid, iid = _mk()
    db = SessionLocal()
    try:
        generate_invoice_lines_from_project(db, project_id=pid, invoice_id=iid)
        inv = db.get(Invoice, iid)
        inv.lines[0].unit_price_ex_vat = Decimal('500.00')
        recalculate_invoice_totals(db, iid)
        db.commit()
    finally:
        db.close()

    resp = client.post(f'/invoices/{iid}/finalize', headers={'accept': 'application/json'}, follow_redirects=False)
    assert resp.status_code == 409


def test_pdf_issued_renders_snapshot_even_if_project_data_changes(monkeypatch):
    _login()
    pid, iid = _mk(mode='FIXED_TOTAL', value=Decimal('1000.00'))
    db = SessionLocal()
    try:
        generate_invoice_lines_from_project(db, project_id=pid, invoice_id=iid)
        db.commit()
    finally:
        db.close()

    offer_issue = client.post(f'/offers/{pid}/finalize', follow_redirects=False)
    invoice_issue = client.post(f'/invoices/{iid}/finalize', follow_redirects=False)
    assert offer_issue.status_code in (302, 303)
    assert invoice_issue.status_code in (302, 303)

    captured = {}

    def _fake_render(*, html, base_url, stylesheet_path):
        captured['html'] = html
        return b'%PDF-1.4 fake'

    monkeypatch.setattr('app.routers.web_documents.render_pdf_from_html', _fake_render)

    db = SessionLocal()
    try:
        pricing = db.query(ProjectPricing).filter(ProjectPricing.project_id == pid).first()
        pricing.fixed_total_price = Decimal('2222.00')
        room = db.query(Room).filter(Room.project_id == pid).first()
        room.floor_area_m2 = Decimal('99.00')
        db.add_all([pricing, room])
        db.commit()
    finally:
        db.close()

    resp = client.get(f'/invoices/{iid}/pdf')
    assert resp.status_code == 200
    assert '1000.00' in captured['html'] or '1 000,00' in captured['html']
    assert '2222.00' not in captured['html']
