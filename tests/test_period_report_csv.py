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


def test_period_report_csv_export():
    login()
    db = SessionLocal()
    try:
        project = Project(name="CSV Project")
        db.add(project)
        db.commit()
        db.refresh(project)
        get_or_create_settings(db)

        invoice = Invoice(
            project_id=project.id,
            invoice_number=f"CSV-INV-1-{uuid.uuid4()}",
            issue_date=date(2024, 2, 15),
            status="sent",
            work_sum_without_moms=Decimal("150.00"),
            moms_amount=Decimal("37.50"),
            rot_amount=Decimal("0.00"),
            client_pays_total=Decimal("187.50"),
        )
        db.add(invoice)
        db.commit()
    finally:
        db.close()

    response = client.get(
        "/reports/period/export.csv",
        params={"from_date": "2024-02-01", "to_date": "2024-02-28"},
    )
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/csv")
    assert "invoice_number" in response.text.splitlines()[0]
    assert "client_pays_total" in response.text.splitlines()[0]
