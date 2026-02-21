from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.main import app
from app.models import Client, Project
from app.services.stats import get_profit_by_client, get_profit_by_month
from tests.db_utils import upgrade_database


def create_session(tmp_path: Path):
    db_path = tmp_path / "stats.sqlite3"
    upgrade_database(f"sqlite:///{db_path}")
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine)
    return TestingSessionLocal()


def test_profit_by_month_basic(tmp_path: Path):
    session = create_session(tmp_path)
    project1 = Project(
        name="P1",
        client_pays_total=Decimal("1000"),
        total_cost=Decimal("400"),
        profit=Decimal("600"),
        created_at=datetime(2024, 1, 10),
    )
    project2 = Project(
        name="P2",
        client_pays_total=Decimal("2000"),
        total_cost=Decimal("800"),
        profit=Decimal("1200"),
        created_at=datetime(2024, 2, 5),
    )
    session.add_all([project1, project2])
    session.commit()

    results = get_profit_by_month(session)
    assert {r["month"] for r in results} == {1, 2}
    jan = next(r for r in results if r["month"] == 1)
    feb = next(r for r in results if r["month"] == 2)

    assert jan["revenue"] == Decimal("1000.00")
    assert jan["total_cost"] == Decimal("400.00")
    assert jan["profit"] == Decimal("600.00")

    assert feb["revenue"] == Decimal("2000.00")
    assert feb["total_cost"] == Decimal("800.00")
    assert feb["profit"] == Decimal("1200.00")

    session.close()


def test_profit_by_client_basic(tmp_path: Path):
    session = create_session(tmp_path)
    client1 = Client(name="Client A")
    client2 = Client(name="Client B")
    project1 = Project(name="P1", client=client1, client_pays_total=Decimal("500"), profit=Decimal("300"))
    project2 = Project(name="P2", client=client2, client_pays_total=Decimal("1000"), profit=Decimal("700"))

    session.add_all([client1, client2, project1, project2])
    session.commit()

    results = get_profit_by_client(session)
    assert len(results) == 2
    res1 = next(r for r in results if r["client_name"] == "Client A")
    res2 = next(r for r in results if r["client_name"] == "Client B")

    assert res1["revenue"] == Decimal("500.00")
    assert res1["profit"] == Decimal("300.00")
    assert res2["revenue"] == Decimal("1000.00")
    assert res2["profit"] == Decimal("700.00")

    session.close()


def test_stats_page_returns_200_after_login():
    client = TestClient(app)
    settings = get_settings()
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )
    response = client.get("/stats/")
    assert response.status_code == 200
