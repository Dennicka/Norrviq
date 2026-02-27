from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.project import Project


def _login(client: TestClient):
    s = get_settings()
    r = client.post('/login', data={'email': s.admin_email, 'password': s.admin_password}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_acceptance_zero_to_offer_invoice_pdf_flow():
    with TestClient(app) as client:
        _login(client)

        c = client.post('/clients/new', data={'name': f'Flow Client {uuid4().hex[:6]}'}, follow_redirects=False)
        assert c.status_code == 303
        client_id = int(c.headers['location'].split('/')[-1])

        p = client.post('/projects/new', data={'name': f'Flow Project {uuid4().hex[:6]}', 'client_id': str(client_id), 'status': 'draft'}, follow_redirects=False)
        assert p.status_code == 303
        project_id = int(p.headers['location'].split('/')[-1])

        room_1 = client.post(f'/projects/{project_id}/rooms/create', data={'name': 'Room 1', 'length_m': '4', 'width_m': '3', 'wall_height_m': '2.5'}, follow_redirects=False)
        room_2 = client.post(f'/projects/{project_id}/rooms/create', data={'name': 'Room 2', 'length_m': '3', 'width_m': '3', 'wall_height_m': '2.5'}, follow_redirects=False)
        assert room_1.status_code == 303
        assert room_2.status_code == 303

        db = SessionLocal()
        try:
            from app.models.worktype import WorkType
            wt = db.query(WorkType).filter(WorkType.is_active.is_(True)).first()
            assert wt is not None
            wt_id = wt.id
        finally:
            db.close()

        add_item = client.post(
            f'/projects/{project_id}/add-work-item',
            data={
                'work_type_id': str(wt_id),
                'scope_mode': 'project',
                'quantity': '12',
                'difficulty_factor': '1.0',
            },
            follow_redirects=False,
        )
        assert add_item.status_code == 303

        recalc = client.post(f'/projects/{project_id}/recalculate-finance', data={}, follow_redirects=False)
        assert recalc.status_code == 303

        compare = client.get(f'/projects/{project_id}/pricing')
        assert compare.status_code == 200
        assert 'Сравнение режимов' in compare.text

        apply_mode = client.post(
            f'/projects/{project_id}/pricing',
            data={'intent': 'apply_best_mode', 'best_metric': 'profit'},
            follow_redirects=False,
        )
        assert apply_mode.status_code == 303

        issue_offer = client.post(f'/offers/{project_id}/issue', data={}, follow_redirects=False)
        assert issue_offer.status_code == 303

        offer_pdf = client.get(f'/offers/{project_id}/pdf')
        assert offer_pdf.status_code == 200
        assert offer_pdf.content.startswith(b'%PDF')

        create_invoice = client.post(
            f'/projects/{project_id}/invoices/create-from-project',
            data={'include_labor': 'true', 'merge_strategy': 'REPLACE_ALL'},
            follow_redirects=False,
        )
        assert create_invoice.status_code == 303
        invoice_id = int(create_invoice.headers['location'].rstrip('/').split('/')[-1])

        issue_invoice = client.post(f'/invoices/{invoice_id}/issue', data={}, follow_redirects=False)
        assert issue_invoice.status_code == 303

        invoice_pdf = client.get(f'/invoices/{invoice_id}/pdf')
        assert invoice_pdf.status_code == 200
        assert invoice_pdf.content.startswith(b'%PDF')

        db = SessionLocal()
        try:
            project = db.get(Project, project_id)
            invoice = db.get(Invoice, invoice_id)
            assert project is not None
            assert invoice is not None
            assert float(project.work_sum_without_moms or 0) > 0
            lines_count = db.query(InvoiceLine).filter(InvoiceLine.invoice_id == invoice_id).count()
            assert lines_count > 0
        finally:
            db.close()
