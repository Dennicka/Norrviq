from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.invoice import Invoice
from app.models.project import Project


def _login(client: TestClient):
    s = get_settings()
    r = client.post('/login', data={'email': s.admin_email, 'password': s.admin_password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_acceptance_flow_hourly_end_to_end():
    with TestClient(app) as client:
        _login(client)
        c = client.post('/clients/new', data={'name': f'Acc Client {uuid4().hex[:6]}'}, follow_redirects=False)
        assert c.status_code == 303
        client_id = int(c.headers['location'].split('/')[-1])
        p = client.post('/projects/new', data={'name': f'Acc Project {uuid4().hex[:6]}','client_id': str(client_id), 'status':'draft'}, follow_redirects=False)
        assert p.status_code == 303
        project_id = int(p.headers['location'].split('/')[-1])
        client.post(f'/projects/{project_id}/rooms/create', data={'name':'Room1','length_m':'4','width_m':'3','wall_height_m':'2.4'}, follow_redirects=False)
        db = SessionLocal()
        try:
            from app.models.worktype import WorkType
            wt = db.query(WorkType).filter(WorkType.is_active.is_(True)).first()
            assert wt is not None
            wt_id = wt.id
        finally:
            db.close()
        client.post(f'/projects/{project_id}/add-work-item', data={'work_type_id': str(wt_id), 'quantity':'10', 'difficulty_factor':'1.0'}, follow_redirects=False)
        client.post(f'/projects/{project_id}/recalculate', data={}, follow_redirects=False)
        client.post(f'/projects/{project_id}/workflow/select-pricing-mode', data={'mode':'HOURLY'}, follow_redirects=False)
        client.post(f'/projects/{project_id}/workflow/create-offer-draft', data={}, follow_redirects=False)
        inv = client.post(f'/projects/{project_id}/invoices/create-from-project', data={'include_labor':'true','merge_strategy':'REPLACE_ALL'}, follow_redirects=False)
        assert inv.status_code == 303
        invoice_id = int(inv.headers['location'].split('/')[-1])
        pdf = client.get(f'/invoices/{invoice_id}/pdf')
        assert pdf.status_code == 200
        db = SessionLocal()
        try:
            invoice = db.get(Invoice, invoice_id)
            assert invoice is not None
            assert float(invoice.client_pays_total or 0) >= 0
            project = db.get(Project, project_id)
            assert project is not None
            assert float(project.total_cost or 0) >= 0
        finally:
            db.close()


def test_acceptance_estimator_flow_includes_materials_cost():
    with TestClient(app) as client:
        _login(client)
        c = client.post('/clients/new', data={'name': f'Mat Client {uuid4().hex[:6]}'}, follow_redirects=False)
        client_id = int(c.headers['location'].split('/')[-1])
        p = client.post('/projects/new', data={'name': f'Mat Project {uuid4().hex[:6]}','client_id': str(client_id), 'status':'draft'}, follow_redirects=False)
        project_id = int(p.headers['location'].split('/')[-1])
        client.post(f'/projects/{project_id}/rooms/create', data={'name':'Room1','length_m':'4','width_m':'3','wall_height_m':'2.4'}, follow_redirects=False)
        db = SessionLocal()
        try:
            from decimal import Decimal
            from app.models.material_norm import MaterialConsumptionNorm
            from app.models.project import ProjectWorkItem
            from app.models.worktype import WorkType
            wt = db.query(WorkType).filter(WorkType.is_active.is_(True)).first()
            assert wt is not None
            item = ProjectWorkItem(project_id=project_id, work_type_id=wt.id, quantity=Decimal('1'), difficulty_factor=Decimal('1'))
            db.add(item)
            db.add(MaterialConsumptionNorm(active=True, is_active=True, material_name='Flow Paint', material_category='paint', applies_to_work_type=wt.code, work_type_code=wt.code, basis_type='wall_area_m2', surface_type='wall', consumption_qty=Decimal('1'), per_basis_qty=Decimal('10'), layers_multiplier_enabled=False, waste_factor_pct=Decimal('0'), consumption_value=Decimal('1'), consumption_unit='per_10_m2', material_unit='L', default_unit_price_sek=Decimal('10'), waste_percent=Decimal('0')))
            db.commit()
            estimate = client.get(f'/projects/{project_id}/estimator')
            assert estimate.status_code == 200
            shopping = client.get(f'/projects/{project_id}/materials-plan')
            assert shopping.status_code == 200
            assert 'Flow Paint' in shopping.text
            from app.services.estimator_engine import build_project_estimate
            summary = build_project_estimate(db, project_id)
            assert summary.totals.materials_ex_vat > 0
        finally:
            db.close()
