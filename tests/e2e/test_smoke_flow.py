import re
from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.invoice import Invoice
from app.models.project import Project
from app.models.worktype import WorkType

from tests.e2e.csrf_helper import csrf_post


settings = get_settings()

_ID_IN_LOCATION_RE = re.compile(r"/(\d+)$")


def _location_id(location: str) -> int:
    match = _ID_IN_LOCATION_RE.search(location)
    assert match, f"Could not parse object id from location: {location}"
    return int(match.group(1))


def _assert_request_id(response):
    assert response.headers.get("X-Request-Id")


def test_smoke_critical_business_flow_end_to_end():
    with TestClient(app) as client:
        login_response = csrf_post(
            client,
            form_url="/login",
            post_url="/login",
            data={"email": settings.admin_email, "password": settings.admin_password},
            follow_redirects=False,
        )
        assert login_response.status_code in (302, 303)
        _assert_request_id(login_response)
    
        client_name = f"E2E Client {uuid4().hex[:8]}"
        create_client_response = csrf_post(
            client,
            form_url="/clients/",
            post_url="/clients/new",
            data={"name": client_name, "email": "client@example.com", "address": "Main street"},
            follow_redirects=False,
        )
        assert create_client_response.status_code == 303
        _assert_request_id(create_client_response)
    
        client_id = _location_id(create_client_response.headers["location"])
    
        create_project_response = csrf_post(
            client,
            form_url="/projects/new",
            post_url="/projects/new",
            data={
                "name": f"E2E Project {uuid4().hex[:6]}",
                "client_id": str(client_id),
                "address": "Project location",
                "status": "draft",
            },
            follow_redirects=False,
        )
        assert create_project_response.status_code == 303
        _assert_request_id(create_project_response)
    
        project_id = _location_id(create_project_response.headers["location"])
    
        db = SessionLocal()
        try:
            work_type = db.query(WorkType).filter(WorkType.is_active.is_(True)).first()
            assert work_type is not None
            work_type_id = work_type.id
        finally:
            db.close()
    
        add_item_response = csrf_post(
            client,
            form_url=f"/projects/{project_id}",
            post_url=f"/projects/{project_id}/add-work-item",
            data={"work_type_id": str(work_type_id), "quantity": "10", "difficulty_factor": "1.0"},
            follow_redirects=False,
        )
        assert add_item_response.status_code == 303
    
        recalc_response = csrf_post(
            client,
            form_url=f"/projects/{project_id}",
            post_url=f"/projects/{project_id}/recalculate",
            data={},
            follow_redirects=False,
        )
        assert recalc_response.status_code == 303
        _assert_request_id(recalc_response)
    
        offer_page = client.get(f"/projects/{project_id}/offer?lang=sv")
        assert offer_page.status_code == 200
        assert "offer-summary" in offer_page.text
        assert "nan" not in offer_page.text.lower()
        _assert_request_id(offer_page)
    
        finalize_offer_response = csrf_post(
            client,
            form_url=f"/projects/{project_id}/offer?lang=sv",
            post_url=f"/offers/{project_id}/finalize",
            data={},
            follow_redirects=False,
        )
        assert finalize_offer_response.status_code == 303
    
        db = SessionLocal()
        try:
            project = db.get(Project, project_id)
            assert project is not None
            assert project.offer_number is not None
            assert re.match(r"^OF-\d{4}-\d{4}$", project.offer_number)
        finally:
            db.close()
    
        create_invoice_response = csrf_post(
            client,
            form_url=f"/projects/{project_id}/invoices/",
            post_url=f"/projects/{project_id}/invoices/create",
            data={
                "issue_date": date.today().isoformat(),
                "status": "draft",
                "work_sum_without_moms": "1000.00",
                "moms_amount": "250.00",
                "rot_amount": "0.00",
                "client_pays_total": "1250.00",
            },
            follow_redirects=False,
        )
        assert create_invoice_response.status_code == 303
    
        db = SessionLocal()
        try:
            invoice = db.query(Invoice).filter(Invoice.project_id == project_id).first()
            assert invoice is not None
            invoice_id = invoice.id
        finally:
            db.close()
    
        finalize_invoice_response = csrf_post(
            client,
            form_url=f"/projects/{project_id}/invoices/{invoice_id}",
            post_url=f"/invoices/{invoice_id}/finalize",
            data={},
            follow_redirects=False,
        )
        assert finalize_invoice_response.status_code == 303
        _assert_request_id(finalize_invoice_response)
    
        invoice_document_response = client.get(f"/projects/{project_id}/invoices/{invoice_id}")
        assert invoice_document_response.status_code == 200
        assert "invoice" in invoice_document_response.text.lower() or "faktura" in invoice_document_response.text.lower()
        _assert_request_id(invoice_document_response)
    
        db = SessionLocal()
        try:
            invoice = db.get(Invoice, invoice_id)
            assert invoice is not None
            assert invoice.invoice_number is not None
            assert re.match(r"^TR-\d{4}-\d{4}$", invoice.invoice_number)
        finally:
            db.close()
