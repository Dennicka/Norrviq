from decimal import Decimal
from uuid import uuid4

from app.db import SessionLocal
from app.models.project import Project
from app.services.pricing import compute_pricing_scenarios, get_or_create_project_pricing
from app.services.pricing_sanity import EHR_UNDEFINED_ZERO_HOURS, MARGIN_UNDEFINED_ZERO_REVENUE, safe_margin_pct


def _make_zero_hours_project() -> int:
    db = SessionLocal()
    try:
        project = Project(name=f"Zero hours {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        db.refresh(project)

        pricing = get_or_create_project_pricing(db, project.id)
        pricing.fixed_total_price = Decimal("1000.00")
        db.commit()
        return project.id
    finally:
        db.close()


def test_effective_hourly_rate_zero_hours_returns_none_and_warns():
    project_id = _make_zero_hours_project()
    db = SessionLocal()
    try:
        _, scenarios = compute_pricing_scenarios(db, project_id)
    finally:
        db.close()

    fixed = next(s for s in scenarios if s.mode == "FIXED_TOTAL")
    assert fixed.effective_hourly_sell_rate is None
    assert any(issue["code"] == EHR_UNDEFINED_ZERO_HOURS and issue["severity"] == "WARN" for issue in fixed.sanity_issues)
    assert fixed.is_valid is True


def test_margin_pct_zero_revenue_returns_none_and_warns():
    margin_pct, issues = safe_margin_pct(profit_ex_vat=Decimal("0.00"), sell_ex_vat=Decimal("0.00"))
    assert margin_pct is None
    assert any(issue.code == MARGIN_UNDEFINED_ZERO_REVENUE and issue.severity == "WARN" for issue in issues)
