from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Project, ProjectWorkItem, Room, WorkType
from app.models.settings import get_or_create_settings
from app.services.estimates import calculate_project_pricing_totals, calculate_work_item
from tests.db_utils import upgrade_database


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "pricing.sqlite3"
    upgrade_database(f"sqlite:///{db_path}")
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


def _work_type(category: str) -> WorkType:
    return WorkType(
        code=f"WT-{category}",
        category=category,
        unit="m2",
        name_ru="Работа",
        name_sv="Arbete",
        hours_per_unit=Decimal("1.0"),
        base_difficulty_factor=Decimal("1.0"),
        is_active=True,
    )


def test_hourly_mode_price_calculation(db_session):
    item = ProjectWorkItem(quantity=Decimal("2"), difficulty_factor=Decimal("1.5"), pricing_mode="hourly", hourly_rate_sek=Decimal("600"))
    wt = _work_type("wall")

    calculate_work_item(item, wt, Decimal("500"), Decimal("250"))

    assert item.calculated_hours == Decimal("3.00")
    assert item.calculated_cost_without_moms == Decimal("1800.00")


def test_area_mode_uses_geometry_targets(db_session):
    room = Room(name="R", floor_area_m2=Decimal("10"), wall_area_m2=Decimal("30"), ceiling_area_m2=Decimal("12"))

    wall_item = ProjectWorkItem(quantity=Decimal("1"), difficulty_factor=Decimal("1"), pricing_mode="area", area_rate_sek=Decimal("100"), room=room)
    calculate_work_item(wall_item, _work_type("wall paint"), Decimal("500"), Decimal("200"))
    assert wall_item.billable_area_m2 == Decimal("30.00")
    assert wall_item.calculated_cost_without_moms == Decimal("3000.00")

    ceiling_item = ProjectWorkItem(quantity=Decimal("1"), difficulty_factor=Decimal("1"), pricing_mode="area", area_rate_sek=Decimal("100"), room=room)
    calculate_work_item(ceiling_item, _work_type("ceiling paint"), Decimal("500"), Decimal("200"))
    assert ceiling_item.billable_area_m2 == Decimal("12.00")

    floor_item = ProjectWorkItem(quantity=Decimal("1"), difficulty_factor=Decimal("1"), pricing_mode="area", area_rate_sek=Decimal("100"), room=room)
    calculate_work_item(floor_item, _work_type("floor protection"), Decimal("500"), Decimal("200"))
    assert floor_item.billable_area_m2 == Decimal("10.00")


def test_fixed_mode_and_margin_calculation(db_session):
    item = ProjectWorkItem(
        quantity=Decimal("2"),
        difficulty_factor=Decimal("1.0"),
        pricing_mode="fixed",
        fixed_price_sek=Decimal("1500"),
        materials_cost_sek=Decimal("100"),
    )
    calculate_work_item(item, _work_type("wall"), Decimal("500"), Decimal("200"))

    assert item.calculated_cost_without_moms == Decimal("1500.00")
    assert item.labor_cost_sek == Decimal("400.00")
    assert item.total_cost_sek == Decimal("500.00")
    assert item.margin_sek == Decimal("1000.00")
    assert item.margin_pct == Decimal("66.67")


def test_project_totals_aggregation(db_session):
    project = Project(name="P")
    wt = _work_type("wall")
    i1 = ProjectWorkItem(quantity=Decimal("1"), difficulty_factor=Decimal("1"), pricing_mode="hourly", hourly_rate_sek=Decimal("100"), work_type=wt)
    i2 = ProjectWorkItem(quantity=Decimal("1"), difficulty_factor=Decimal("1"), pricing_mode="fixed", fixed_price_sek=Decimal("80"), work_type=wt)
    project.work_items = [i1, i2]
    db_session.add(project)
    db_session.commit()

    settings = get_or_create_settings(db_session)
    for item in project.work_items:
        calculate_work_item(item, wt, Decimal("100"), Decimal(str(settings.internal_labor_cost_rate_sek)))

    totals = calculate_project_pricing_totals(project)
    assert totals.total_labor_hours == Decimal("2.00")
    assert totals.total_price_sek == Decimal("180.00")
    assert totals.total_cost_sek > Decimal("0")
    assert totals.total_margin_sek == totals.total_price_sek - totals.total_cost_sek
