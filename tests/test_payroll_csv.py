from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.config import get_settings

from app.db import SessionLocal
from app.models import Project, ProjectWorkerAssignment, Worker
from app.models.settings import get_or_create_settings
from app.main import app
from tests.db_utils import clear_selected_tables


client = TestClient(app)
settings = get_settings()


def reset_db():
    db = SessionLocal()
    try:
        clear_selected_tables(
            db,
            {
                "project_worker_assignments",
                "project_cost_items",
                "project_work_items",
                "project_pricing",
                "project_buffer_settings",
                "project_execution_profiles",
                "rooms",
                "invoices",
                "projects",
                "workers",
                "work_types",
                "materials",
                "legal_notes",
                "cost_categories",
                "users",
                "settings",
                "clients",
            },
        )
    finally:
        db.close()


def login():
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def create_sample_data():
    reset_db()
    db = SessionLocal()
    try:
        get_or_create_settings(db)
        worker = Worker(name="CSV Worker", role="Tester", hourly_rate=Decimal("150"))
        project = Project(
            name="CSV Project",
            planned_start_date=date(2024, 6, 1),
            planned_end_date=date(2024, 6, 30),
        )
        assignment = ProjectWorkerAssignment(
            project=project,
            worker=worker,
            planned_hours=Decimal("5"),
            actual_hours=Decimal("4"),
        )
        db.add_all([worker, project, assignment])
        db.commit()
    finally:
        db.close()


def test_payroll_summary_csv():
    create_sample_data()
    login()

    response = client.get(
        "/payroll/summary/export.csv",
        params={"from_date": "2024-06-01", "to_date": "2024-06-30"},
    )

    assert response.status_code == 200
    assert response.headers.get("Content-Type", "").startswith("text/csv")
    assert response.text.splitlines()[0] == (
        "worker_name,worker_role,total_planned_hours,total_actual_hours,hourly_rate,gross_pay,employer_taxes,total_employer_cost,net_tax_percent,net_pay_approx"
    )
