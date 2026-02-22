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
        settings_obj = get_or_create_settings(db)
        settings_obj.employer_contributions_percent = Decimal("31.42")
        db.commit()

        worker = Worker(name="Payroll Worker", role="Painter", hourly_rate=Decimal("200"))
        project = Project(
            name="Payroll Project",
            planned_start_date=date(2024, 6, 1),
            planned_end_date=date(2024, 6, 30),
        )
        assignment = ProjectWorkerAssignment(
            project=project,
            worker=worker,
            planned_hours=Decimal("8"),
            actual_hours=Decimal("10"),
        )

        db.add_all([worker, project, assignment])
        db.commit()
        db.refresh(worker)
        return worker
    finally:
        db.close()


def test_payroll_summary_page_contains_worker():
    worker = create_sample_data()
    login()

    response = client.get(
        "/payroll/summary/",
        params={"from_date": "2024-06-01", "to_date": "2024-06-30"},
    )

    assert response.status_code == 200
    assert worker.name in response.text


def test_payroll_worker_detail_shows_project():
    worker = create_sample_data()
    login()

    response = client.get(
        f"/payroll/worker/{worker.id}/",
        params={"from_date": "2024-06-01", "to_date": "2024-06-30"},
    )

    assert response.status_code == 200
    assert "Payroll Project" in response.text
