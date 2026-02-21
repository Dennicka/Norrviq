from datetime import date
from decimal import Decimal

import pytest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.db_utils import upgrade_database

from app.models import Project, ProjectWorkerAssignment, Worker

from app.models.settings import Settings, get_or_create_settings
from app.services.payroll import compute_worker_summary_for_period


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "unit.sqlite3"
    upgrade_database(f"sqlite:///{db_path}")
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


def test_compute_worker_summary_for_period(db_session):
    settings: Settings = get_or_create_settings(db_session)
    settings.employer_contributions_percent = Decimal("30")
    settings.default_worker_tax_percent_for_net = Decimal("25")
    db_session.commit()

    worker = Worker(name="Tester", hourly_rate=Decimal("200"))
    project1 = Project(name="Project A", planned_start_date=date(2024, 6, 1), planned_end_date=date(2024, 6, 30))
    project2 = Project(name="Project B", planned_start_date=date(2024, 6, 15), planned_end_date=date(2024, 7, 15))

    assignment1 = ProjectWorkerAssignment(
        project=project1, worker=worker, planned_hours=Decimal("10"), actual_hours=Decimal("12")
    )
    assignment2 = ProjectWorkerAssignment(
        project=project2, worker=worker, planned_hours=Decimal("5"), actual_hours=Decimal("6")
    )

    db_session.add_all([worker, project1, project2, assignment1, assignment2])
    db_session.commit()

    summary = compute_worker_summary_for_period(
        db_session, worker, settings, date(2024, 6, 1), date(2024, 6, 30)
    )

    assert summary.total_planned_hours == Decimal("15.00")
    assert summary.total_actual_hours == Decimal("18.00")
    assert summary.gross_pay == Decimal("3600.00")
    assert summary.employer_taxes == Decimal("1080.00")
    assert summary.total_employer_cost == Decimal("4680.00")
    assert summary.net_pay_approx == Decimal("2700.00")
