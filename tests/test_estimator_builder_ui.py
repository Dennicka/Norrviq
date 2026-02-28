from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType


client = TestClient(app)
settings = get_settings()


def _login() -> None:
    client.post('/login', data={'username': settings.admin_username, 'password': settings.admin_password})


def _seed() -> tuple[int, int]:
    db = SessionLocal()
    try:
        project = Project(name=f'Estimator UI {uuid4().hex[:6]}')
        room = Room(project=project, name='Room A', floor_area_m2=Decimal('12'), wall_area_m2=Decimal('24'), ceiling_area_m2=Decimal('12'), wall_perimeter_m=Decimal('14'))
        wt = WorkType(code=f'PAINT_CEILING_{uuid4().hex[:4]}', name_ru='Покраска потолка', name_sv='Måla tak', category='paint', unit='m2', hours_per_unit=Decimal('0.5'), is_active=True)
        db.add_all([project, room, wt])
        db.commit()
        return project.id, wt.id
    finally:
        db.close()


def test_estimator_builder_page_and_recalc_flow():
    _login()
    project_id, wt_id = _seed()
    resp = client.get(f'/projects/{project_id}/estimator')
    assert resp.status_code == 200

    add = client.post(f'/projects/{project_id}/estimator/work-items/add', data={'work_type_id': str(wt_id)}, follow_redirects=False)
    assert add.status_code == 303

    db = SessionLocal()
    try:
        item = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).first()
        assert item is not None
        update = client.post(
            f'/projects/{project_id}/estimator/work-items/{item.id}/update',
            data={'scope_mode': 'PROJECT', 'basis_type': 'ceiling_area_m2', 'pricing_mode': 'HOURLY'},
            follow_redirects=False,
        )
        assert update.status_code == 303
    finally:
        db.close()

    recalc = client.post(f'/projects/{project_id}/estimator/recalculate', data={}, follow_redirects=False)
    assert recalc.status_code == 303

    db = SessionLocal()
    try:
        item = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).first()
        assert Decimal(str(item.calculated_qty or 0)) > 0
        assert Decimal(str(item.calculated_hours or 0)) > 0
        assert Decimal(str(item.calculated_sell_ex_vat or 0)) >= 0
    finally:
        db.close()
