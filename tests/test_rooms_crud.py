from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Project, ProjectWorkItem, Room, WorkType
from app.services.rooms import recalc_room_dimensions


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


def test_room_crud_flow(db_session):
    project = Project(name="Test project")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    room = Room(
        project_id=project.id,
        name="Living",
        floor_area_m2=Decimal("20.00"),
        wall_perimeter_m=Decimal("18.00"),
        wall_height_m=Decimal("2.50"),
    )
    recalc_room_dimensions(room)
    db_session.add(room)
    db_session.commit()
    db_session.refresh(room)

    assert room.wall_area_m2 == Decimal("45.00")
    assert room.ceiling_area_m2 == Decimal("20.00")
    assert room.baseboard_length_m == Decimal("18.00")

    room.wall_height_m = Decimal("3.00")
    recalc_room_dimensions(room)
    db_session.add(room)
    db_session.commit()
    db_session.refresh(room)

    assert room.wall_area_m2 == Decimal("54.00")

    db_session.delete(room)
    db_session.commit()
    assert db_session.query(Room).count() == 0


def test_work_item_with_room(db_session):
    project = Project(name="Project with room")
    work_type = WorkType(
        code="CODE",
        category="general",
        unit="m2",
        name_ru="Тест",
        name_sv="Test",
        description_ru=None,
        description_sv=None,
        hours_per_unit=Decimal("1.0"),
        base_difficulty_factor=Decimal("1.0"),
    )
    room = Room(project=project, name="Room", floor_area_m2=Decimal("12"))
    recalc_room_dimensions(room)

    db_session.add_all([project, work_type, room])
    db_session.commit()
    db_session.refresh(room)

    item = ProjectWorkItem(project_id=project.id, work_type_id=work_type.id, room_id=room.id, quantity=Decimal("5"), difficulty_factor=Decimal("1.0"))
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    assert item.room_id == room.id
    assert item.room == room
