from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from tests.db_utils import upgrade_database

from app.models import Project, ProjectWorkerAssignment, Worker

from app.models.settings import get_or_create_settings
from app.services.workers import get_worker_aggregates
from app.config import get_settings


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "unit.sqlite3"
    upgrade_database(f"sqlite:///{db_path}")
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


def test_workers_aggregation_uses_default_rate(db_session):
    settings = get_or_create_settings(db_session)
    settings.default_worker_hourly_rate = Decimal("200")
    settings.default_worker_tax_percent_for_net = Decimal("30")
    db_session.commit()

    worker = Worker(name="Worker X")
    project = Project(name="Project X")
    assignment = ProjectWorkerAssignment(project=project, worker=worker, actual_hours=Decimal("10"))
    db_session.add_all([project, worker, assignment])
    db_session.commit()

    aggregates = get_worker_aggregates(db_session, [worker], settings)
    stats = aggregates[worker.id]

    assert stats["total_hours"] == Decimal("10.00")
    assert stats["total_gross"] == Decimal("2000.00")
    assert stats["approx_net"] == Decimal("1400.00")


def test_workers_page_returns_200():
    client = TestClient(app)
    settings = get_settings()
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )
    response = client.get("/workers/")
    assert response.status_code == 200
