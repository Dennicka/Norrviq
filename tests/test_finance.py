from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Project, ProjectWorkerAssignment, Worker
from app.models.cost import CostCategory, ProjectCostItem
from app.models.settings import get_or_create_settings
from app.services.finance import (
    calculate_cost_items,
    calculate_project_financials,
    calculate_salary_costs,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


def test_calculate_salary_costs_basic(db_session):
    settings = get_or_create_settings(db_session)
    settings.default_worker_hourly_rate = Decimal("200")
    settings.employer_contributions_percent = Decimal("30")
    db_session.commit()

    worker = Worker(name="Worker A")
    project = Project(name="Test Project")
    assignment = ProjectWorkerAssignment(project=project, worker=worker, actual_hours=Decimal("10"))

    db_session.add_all([project, worker, assignment])
    db_session.commit()

    result = calculate_salary_costs(db_session, project)

    assert result["salary_fund"] == Decimal("2000.00")
    assert result["employer_taxes"] == Decimal("600.00")
    assert result["total_salary_cost"] == Decimal("2600.00")


def test_calculate_cost_items_grouping(db_session):
    project = Project(name="Costs Project")
    categories = {
        code: CostCategory(code=code, name_ru=code, name_sv=code) for code in ["MATERIALS", "FUEL", "PARKING", "OTHER"]
    }

    items = [
        ProjectCostItem(project=project, category=categories["MATERIALS"], title="Paint", amount=Decimal("100")),
        ProjectCostItem(project=project, category=categories["FUEL"], title="Fuel", amount=Decimal("50")),
        ProjectCostItem(project=project, category=categories["PARKING"], title="Parking", amount=Decimal("20")),
        ProjectCostItem(project=project, category=categories["OTHER"], title="Misc", amount=Decimal("10")),
    ]

    db_session.add_all([project] + list(categories.values()) + items)
    db_session.commit()

    result = calculate_cost_items(db_session, project)

    assert result["materials_cost"] == Decimal("100.00")
    assert result["fuel_cost"] == Decimal("50.00")
    assert result["parking_cost"] == Decimal("20.00")
    assert result["other_cost"] == Decimal("10.00")
    assert result["total_extra_cost"] == Decimal("180.00")


def test_calculate_project_financials(db_session):
    settings = get_or_create_settings(db_session)
    settings.default_worker_hourly_rate = Decimal("200")
    settings.employer_contributions_percent = Decimal("30")
    settings.default_overhead_percent = Decimal("10")
    db_session.commit()

    worker = Worker(name="Worker B")
    project = Project(name="Finance Project", client_pays_total=Decimal("20000"))

    categories = {
        code: CostCategory(code=code, name_ru=code, name_sv=code) for code in ["MATERIALS", "FUEL"]
    }

    assignment = ProjectWorkerAssignment(project=project, worker=worker, actual_hours=Decimal("10"))
    cost_materials = ProjectCostItem(project=project, category=categories["MATERIALS"], title="Paint", amount=Decimal("1000"))
    cost_fuel = ProjectCostItem(project=project, category=categories["FUEL"], title="Fuel", amount=Decimal("500"))

    db_session.add_all([project, worker, assignment] + list(categories.values()) + [cost_materials, cost_fuel])
    db_session.commit()

    calculate_project_financials(db_session, project)

    assert project.salary_fund == Decimal("2000.00")
    assert project.materials_cost == Decimal("1000.00")
    assert project.fuel_cost == Decimal("500.00")
    assert project.total_cost == Decimal("4510.00")
    assert project.profit == Decimal("15490.00")
    assert project.margin_percent == Decimal("77.45")
