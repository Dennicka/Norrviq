from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Client, Project, ProjectWorkItem, WorkType
from app.models.settings import get_or_create_settings
from app.services.estimates import calculate_project_totals, calculate_work_item


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


def test_calculate_work_item_basic(db_session):
    work_type = WorkType(
        code="PAINT",
        category="paint",
        unit="m2",
        name_ru="Покраска",
        name_sv="Målning",
        description_ru=None,
        description_sv=None,
        hours_per_unit=Decimal("0.5"),
        base_difficulty_factor=Decimal("1.0"),
    )
    project_item = ProjectWorkItem(quantity=Decimal("10"), difficulty_factor=Decimal("1.2"), work_type=work_type)

    hourly_rate_company = Decimal("500")
    calculate_work_item(project_item, work_type, hourly_rate_company)

    assert project_item.calculated_hours == Decimal("6.00")
    assert project_item.calculated_cost_without_moms == Decimal("3000.00")


def test_calculate_project_totals_with_rot(db_session):
    settings = get_or_create_settings(db_session)
    settings.moms_percent = Decimal("25")
    settings.rot_percent = Decimal("50")
    settings.hourly_rate_company = Decimal("500")
    db_session.commit()

    client = Client(name="Иван Иванов", is_private_person=True, is_rot_eligible=True)
    project = Project(name="Проект с ROT", use_rot=True, client=client)

    work_type = WorkType(
        code="PREP",
        category="prep",
        unit="m2",
        name_ru="Подготовка",
        description_ru=None,
        name_sv="Förberedelse",
        description_sv=None,
        hours_per_unit=Decimal("0.5"),
        base_difficulty_factor=Decimal("1.0"),
    )
    item1 = ProjectWorkItem(quantity=Decimal("10"), difficulty_factor=Decimal("1.0"), work_type=work_type)
    item2 = ProjectWorkItem(quantity=Decimal("4"), difficulty_factor=Decimal("1.5"), work_type=work_type)

    project.work_items.extend([item1, item2])

    hourly_rate = Decimal(str(settings.hourly_rate_company))
    calculate_work_item(item1, work_type, hourly_rate)
    calculate_work_item(item2, work_type, hourly_rate)

    db_session.add(project)
    db_session.commit()

    totals = calculate_project_totals(db_session, project)

    expected_sum = item1.calculated_cost_without_moms + item2.calculated_cost_without_moms
    expected_moms = (expected_sum * Decimal("0.25")).quantize(Decimal("0.01"))
    expected_rot = (expected_sum * Decimal("0.50")).quantize(Decimal("0.01"))
    expected_total = (expected_sum + expected_moms - expected_rot).quantize(Decimal("0.01"))

    assert totals.work_sum_without_moms == expected_sum
    assert totals.moms_amount == expected_moms
    assert totals.rot_amount == expected_rot
    assert totals.client_pays_total == expected_total


def test_calculate_project_totals_without_rot(db_session):
    settings = get_or_create_settings(db_session)
    settings.moms_percent = Decimal("25")
    settings.rot_percent = Decimal("50")
    settings.hourly_rate_company = Decimal("500")
    db_session.commit()

    client = Client(name="Компания", is_private_person=False, is_rot_eligible=False)
    project = Project(name="Проект без ROT", use_rot=True, client=client)

    work_type = WorkType(
        code="CLEAN",
        category="cleaning",
        unit="m2",
        name_ru="Уборка",
        description_ru=None,
        name_sv="Städning",
        description_sv=None,
        hours_per_unit=Decimal("1.0"),
        base_difficulty_factor=Decimal("1.0"),
    )
    item = ProjectWorkItem(quantity=Decimal("2"), difficulty_factor=Decimal("1.0"), work_type=work_type)
    project.work_items.append(item)

    hourly_rate = Decimal(str(settings.hourly_rate_company))
    calculate_work_item(item, work_type, hourly_rate)

    db_session.add(project)
    db_session.commit()

    totals = calculate_project_totals(db_session, project)

    expected_sum = item.calculated_cost_without_moms
    expected_moms = (expected_sum * Decimal("0.25")).quantize(Decimal("0.01"))
    expected_total = (expected_sum + expected_moms).quantize(Decimal("0.01"))

    assert totals.work_sum_without_moms == expected_sum
    assert totals.moms_amount == expected_moms
    assert totals.rot_amount == Decimal("0")
    assert totals.client_pays_total == expected_total
