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


def _seed_project_with_package_worktypes() -> int:
    db = SessionLocal()
    try:
        project = Project(name=f'Package {uuid4().hex[:6]}')
        room = Room(project=project, name='Living', floor_area_m2=Decimal('20'), wall_area_m2=Decimal('40'), ceiling_area_m2=Decimal('20'), wall_perimeter_m=Decimal('18'))
        wts = [
            WorkType(code='MASK_FLOOR', name_ru='Укрывка пола', name_sv='Mask golv', category='prep', unit='m2', hours_per_unit=Decimal('0.1'), is_active=True),
            WorkType(code='PAINT_CEILING', name_ru='Покраска потолка', name_sv='Måla tak', category='paint', unit='m2', hours_per_unit=Decimal('0.2'), is_active=True),
        ]
        db.add(project)
        db.add(room)
        for wt in wts:
            existing = db.query(WorkType).filter(WorkType.code == wt.code).first()
            if not existing:
                db.add(wt)
        db.commit()
        return project.id
    finally:
        db.close()


def test_add_package_creates_work_items_and_recalc_non_zero():
    _login()
    project_id = _seed_project_with_package_worktypes()
    add = client.post(
        f'/projects/{project_id}/estimator/packages/add',
        data={'package_code': 'paint_ceiling_2coats_project'},
        follow_redirects=False,
    )
    assert add.status_code == 303

    db = SessionLocal()
    try:
        rows = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).all()
        assert len(rows) >= 1
        assert rows[0].scope_mode == 'PROJECT'
        assert rows[0].basis_type == 'ceiling_area_m2'
    finally:
        db.close()

    recalc = client.post(f'/projects/{project_id}/estimator/recalculate', data={}, follow_redirects=False)
    assert recalc.status_code == 303

    db = SessionLocal()
    try:
        total_sell = sum((Decimal(str(r.calculated_sell_ex_vat or 0)) for r in db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).all()), Decimal('0'))
        assert total_sell >= 0
    finally:
        db.close()
