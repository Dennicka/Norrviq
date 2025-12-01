from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Project, ProjectWorkerAssignment, Worker
from app.models.cost import CostCategory, ProjectCostItem
from app.models.project import ProjectWorkItem
from app.models.settings import get_or_create_settings
from app.services.finance import (
    calculate_cost_items,
    calculate_salary_costs,
    compute_project_finance,
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

    result = calculate_salary_costs(db_session, project, settings=settings)

    assert result["salary_fund"] == Decimal("2000.00")
    assert result["employer_taxes"] == Decimal("600.00")
    assert result["total_salary_cost"] == Decimal("2600.00")


def test_calculate_cost_items_grouping(db_session):
    project = Project(name="Costs Project")
    categories = {
        code: CostCategory(code=code, name_ru=code, name_sv=code)
        for code in ["MATERIALS", "TRANSPORT", "OTHER"]
    }

    items = [
        ProjectCostItem(project=project, category=categories["MATERIALS"], title="Paint", amount=Decimal("100")),
        ProjectCostItem(project=project, category=categories["TRANSPORT"], title="Fuel", amount=Decimal("50")),
        ProjectCostItem(project=project, category=categories["OTHER"], title="Misc", amount=Decimal("10")),
    ]

    db_session.add_all([project] + list(categories.values()) + items)
    db_session.commit()

    result = calculate_cost_items(db_session, project)

    assert result["materials_cost"] == Decimal("100.00")
    assert result["transport_cost"] == Decimal("50.00")
    assert result["other_cost"] == Decimal("10.00")
    assert result["total_extra_cost"] == Decimal("160.00")


def test_compute_project_finance(db_session):
    settings = get_or_create_settings(db_session)
    settings.default_worker_hourly_rate = Decimal("200")
    settings.employer_contributions_percent = Decimal("30")
    settings.default_overhead_percent = Decimal("10")
    settings.moms_percent = Decimal("25")
    settings.rot_percent = Decimal("50")
    db_session.commit()

    project = Project(name="Finance Project", use_rot=True)
    worker = Worker(name="Worker B", hourly_rate=Decimal("200"))
    assignment = ProjectWorkerAssignment(project=project, worker=worker, actual_hours=Decimal("5"))

    work_type_cost = ProjectWorkItem(
        project=project, work_type_id=1, quantity=1, difficulty_factor=1, calculated_cost_without_moms=Decimal("1000")
    )

    categories = {
        code: CostCategory(code=code, name_ru=code, name_sv=code)
        for code in ["MATERIALS", "TRANSPORT", "OTHER"]
    }
    cost_materials = ProjectCostItem(project=project, category=categories["MATERIALS"], title="Paint", amount=Decimal("200"))
    cost_transport = ProjectCostItem(
        project=project, category=categories["TRANSPORT"], title="Fuel", amount=Decimal("100")
    )
    cost_other = ProjectCostItem(project=project, category=categories["OTHER"], title="Misc", amount=Decimal("50"))

    db_session.add_all(
        [project, worker, assignment, work_type_cost]
        + list(categories.values())
        + [cost_materials, cost_transport, cost_other]
    )
    db_session.commit()

    summary = compute_project_finance(db_session, project, settings=settings)

    assert summary.work_sum_without_moms == Decimal("1000.00")
    assert summary.client_pays_total == Decimal("750.00")
    assert summary.materials_cost == Decimal("200.00")
    assert summary.transport_cost == Decimal("100.00")
    assert summary.other_cost == Decimal("50.00")
    assert summary.salary_fund == Decimal("1000.00")
    assert summary.total_salary_cost == Decimal("1300.00")
    assert summary.overhead_cost == Decimal("165.00")
    assert summary.total_expenses == Decimal("1815.00")
    assert summary.profit == Decimal("-1065.00")
    assert summary.margin_percent == Decimal("-142.00")


def test_compute_project_finance_margin_none(db_session):
    project = Project(name="Zero Project")
    db_session.add(project)
    db_session.commit()

    summary = compute_project_finance(db_session, project)

    assert summary.client_pays_total == Decimal("0.00")
    assert summary.margin_percent is None
