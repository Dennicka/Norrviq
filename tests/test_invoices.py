from datetime import date
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Invoice, Project
from app.models.settings import get_or_create_settings

client = TestClient(app)
settings = get_settings()


def login():
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def test_create_invoice_and_list():
    login()
    db = SessionLocal()
    try:
        project = Project(name="Invoice project")
        db.add(project)
        db.commit()
        db.refresh(project)
        get_or_create_settings(db)
        project_id = project.id
    finally:
        db.close()

    invoice_number = f"INV-TEST-{uuid.uuid4()}"

    response = client.post(
        f"/projects/{project_id}/invoices/create",
        data={
            "invoice_number": invoice_number,
            "issue_date": date.today().isoformat(),
            "status": "sent",
            "work_sum_without_moms": "100.00",
            "moms_amount": "25.00",
            "rot_amount": "0.00",
            "client_pays_total": "125.00",
        },
        follow_redirects=False,
    )
    assert response.status_code in (303, 200)

    db = SessionLocal()
    try:
        invoice = db.query(Invoice).filter(Invoice.project_id == project_id).first()
        assert invoice is not None
        assert invoice.client_pays_total == Decimal("125.00")
    finally:
        db.close()

    list_response = client.get(f"/projects/{project_id}/invoices/")
    assert list_response.status_code == 200
    assert invoice_number in list_response.text
