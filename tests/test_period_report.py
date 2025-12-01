from datetime import date
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Invoice, Project
from app.models.settings import get_or_create_settings
from app.routers.web_reports import _calculate_summary

client = TestClient(app)
settings = get_settings()


def login():
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def test_period_report_summary_and_page():
    login()
    db = SessionLocal()
    try:
        project1 = Project(name="Period P1")
        project2 = Project(name="Period P2")
        db.add_all([project1, project2])
        db.commit()
        db.refresh(project1)
        db.refresh(project2)

        settings_obj = get_or_create_settings(db)

        inv1 = Invoice(
            project_id=project1.id,
            invoice_number=f"PR-INV-1-{uuid.uuid4()}",
            issue_date=date(2024, 1, 10),
            status="sent",
            work_sum_without_moms=Decimal("100.00"),
            moms_amount=Decimal("25.00"),
            rot_amount=Decimal("0.00"),
            client_pays_total=Decimal("125.00"),
        )
        inv2 = Invoice(
            project_id=project2.id,
            invoice_number=f"PR-INV-2-{uuid.uuid4()}",
            issue_date=date(2024, 1, 20),
            status="paid",
            work_sum_without_moms=Decimal("200.00"),
            moms_amount=Decimal("50.00"),
            rot_amount=Decimal("10.00"),
            client_pays_total=Decimal("240.00"),
        )
        inv3 = Invoice(
            project_id=project1.id,
            invoice_number=f"PR-INV-3-{uuid.uuid4()}",
            issue_date=date(2024, 3, 5),
            status="sent",
            work_sum_without_moms=Decimal("300.00"),
            moms_amount=Decimal("75.00"),
            rot_amount=Decimal("0.00"),
            client_pays_total=Decimal("375.00"),
        )

        db.add_all([inv1, inv2, inv3])
        db.commit()

        invoices_in_range = [inv1, inv2]
        summary = _calculate_summary(
            db,
            invoices_in_range,
            settings=settings_obj,
            from_date=date(2024, 1, 1),
            to_date=date(2024, 1, 31),
        )
        assert summary.total_client_pays == Decimal("365.00")
        assert summary.total_work_sum_without_moms == Decimal("300.00")
        assert summary.total_moms_amount == Decimal("75.00")
        assert summary.total_rot_amount == Decimal("10.00")
    finally:
        db.close()

    response = client.get(
        "/reports/period/",
        params={"from_date": "2024-01-01", "to_date": "2024-01-31"},
    )
    assert response.status_code == 200
    assert "Periodrapport" in response.text or "Отчёт за период" in response.text
