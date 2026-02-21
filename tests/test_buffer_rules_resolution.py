from datetime import datetime, timedelta
from uuid import uuid4
from decimal import Decimal

from app.db import SessionLocal
from app.models.buffer_rule import BufferRule
from app.models.project import Project
from app.models.worktype import WorkType
from app.services.buffer_rules import resolve_effective_buffer
from app.services.pricing import compute_project_baseline


def _project(db):
    p = Project(name="Buffer Resolution Project")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _worktype(db):
    wt = WorkType(
        code=f"WT-BUFFER-{uuid4().hex[:8]}",
        category="test",
        unit="m2",
        name_ru="Тест",
        name_sv="Test",
        hours_per_unit=Decimal("1.00"),
        is_active=True,
    )
    db.add(wt)
    db.commit()
    db.refresh(wt)
    return wt


def test_resolve_effective_buffer_scoping_priority_and_tie_break():
    db = SessionLocal()
    try:
        db.query(BufferRule).delete()
        db.commit()
        project = _project(db)
        global_rule = BufferRule(kind="RISK", basis="INTERNAL_COST", unit="PERCENT", value=Decimal("10.00"), scope_type="GLOBAL", scope_id=None, priority=10, is_active=True)
        project_rule_old = BufferRule(kind="RISK", basis="INTERNAL_COST", unit="PERCENT", value=Decimal("20.00"), scope_type="PROJECT", scope_id=project.id, priority=50, is_active=True)
        project_rule_new = BufferRule(kind="RISK", basis="INTERNAL_COST", unit="PERCENT", value=Decimal("30.00"), scope_type="PROJECT", scope_id=project.id, priority=50, is_active=True)
        now = datetime.utcnow()
        project_rule_old.created_at = now
        project_rule_new.created_at = now + timedelta(seconds=1)
        db.add_all([global_rule, project_rule_old, project_rule_new])
        db.commit()

        result = resolve_effective_buffer(db, project_id=project.id)

        assert result.applied_rule_id == project_rule_new.id
        assert result.scope == "project"
        assert result.buffer_value == Decimal("30.00")
    finally:
        db.close()


def test_resolve_effective_buffer_worktype_overrides_project_and_global():
    db = SessionLocal()
    try:
        db.query(BufferRule).delete()
        db.commit()
        project = _project(db)
        worktype = _worktype(db)
        db.add_all(
            [
                BufferRule(kind="RISK", basis="INTERNAL_COST", unit="PERCENT", value=Decimal("5.00"), scope_type="GLOBAL", scope_id=None, priority=1, is_active=True),
                BufferRule(kind="RISK", basis="INTERNAL_COST", unit="PERCENT", value=Decimal("10.00"), scope_type="PROJECT", scope_id=project.id, priority=10, is_active=True),
                BufferRule(kind="RISK", basis="INTERNAL_COST", unit="PERCENT", value=Decimal("25.00"), scope_type="WORKTYPE", scope_id=worktype.id, priority=1, is_active=True),
            ]
        )
        db.commit()

        result = resolve_effective_buffer(db, project_id=project.id, worktype_id=worktype.id)
        assert result.scope == "worktype"
        assert result.buffer_value == Decimal("25.00")
    finally:
        db.close()


def test_baseline_unchanged_without_rules():
    db = SessionLocal()
    try:
        db.query(BufferRule).delete()
        db.commit()
        project = _project(db)

        baseline = compute_project_baseline(db, project.id, include_materials=True, include_travel_setup_buffers=True)

        assert baseline.buffers_hours_total == Decimal("0.00")
        assert baseline.buffers_cost_total == Decimal("0.00")
        assert baseline.raw_labor_hours_total == baseline.labor_hours_total
        assert baseline.raw_internal_cost == baseline.internal_total_cost
    finally:
        db.close()
