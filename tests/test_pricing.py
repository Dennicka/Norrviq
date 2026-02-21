from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.cost import CostCategory, ProjectCostItem
from app.models.project import Project, ProjectWorkItem
from app.models.project_pricing import ProjectPricing
from app.models.pricing_policy import PricingPolicy
from app.models.room import Room
from app.models.user import User
from app.models.worker import Worker
from app.models.worktype import WorkType
from app.security import hash_password
from app.services.estimates import calculate_work_item
from app.services.pricing import (
    PRICING_MODES,
    WARNING_MISSING_ITEMS,
    WARNING_MISSING_UNITS_M2,
    WARNING_MISSING_UNITS_ROOMS,
    WARNING_MISSING_BASELINE,
    DesiredInput,
    PricingValidationError,
    compute_conversions,
    compute_project_baseline,
    compute_pricing_scenarios,
    get_or_create_project_pricing,
    update_project_pricing,
    evaluate_floor,
)

client = TestClient(app)
settings = get_settings()


def login(email: str, password: str):
    return client.post(
        "/login",
        data={"username": email, "password": password, "next": "/projects/"},
        follow_redirects=False,
    )


def ensure_user(email: str, role: str, password: str = "test-password"):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            db.add(User(email=email, password_hash=hash_password(password), role=role))
            db.commit()
    finally:
        db.close()


def _make_golden_project() -> int:
    db = SessionLocal()
    try:
        project = Project(name=f"Golden pricing {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        db.refresh(project)

        wt = WorkType(
            code=f"WT-{uuid4().hex[:6]}",
            category="paint",
            unit="m2",
            name_ru="Тест",
            name_sv="Test",
            description_ru=None,
            description_sv=None,
            hours_per_unit=Decimal("2.00"),
            base_difficulty_factor=Decimal("1.00"),
            is_active=True,
        )
        db.add(wt)

        room1 = Room(project_id=project.id, name="R1", floor_area_m2=Decimal("20.00"))
        room2 = Room(project_id=project.id, name="R2", floor_area_m2=Decimal("30.00"))
        db.add_all([room1, room2])
        db.flush()

        item1 = ProjectWorkItem(
            project_id=project.id,
            room_id=room1.id,
            work_type_id=wt.id,
            quantity=Decimal("3.00"),
            difficulty_factor=Decimal("1.00"),
        )
        item2 = ProjectWorkItem(
            project_id=project.id,
            room_id=room2.id,
            work_type_id=wt.id,
            quantity=Decimal("2.00"),
            difficulty_factor=Decimal("1.00"),
        )
        calculate_work_item(item1, wt, Decimal("550.00"))
        calculate_work_item(item2, wt, Decimal("550.00"))
        db.add_all([item1, item2])

        worker = Worker(name=f"Worker {uuid4().hex[:5]}", hourly_rate=Decimal("200.00"), is_active=True)
        db.add(worker)
        db.flush()

        from app.models.project import ProjectWorkerAssignment

        db.add(
            ProjectWorkerAssignment(
                project_id=project.id,
                worker_id=worker.id,
                actual_hours=Decimal("10.00"),
                planned_hours=Decimal("10.00"),
            )
        )

        materials = db.query(CostCategory).filter(CostCategory.code == "MATERIALS").first()
        if not materials:
            materials = CostCategory(code="MATERIALS", name_ru="Материалы", name_sv="Material")
            db.add(materials)
            db.flush()
        overhead = db.query(CostCategory).filter(CostCategory.code == "OTHER").first()
        if not overhead:
            overhead = CostCategory(code="OTHER", name_ru="Прочее", name_sv="Other")
            db.add(overhead)
            db.flush()

        db.add(ProjectCostItem(project_id=project.id, cost_category_id=materials.id, title="M", amount=Decimal("100.00"), is_material=True))
        db.add(ProjectCostItem(project_id=project.id, cost_category_id=overhead.id, title="O", amount=Decimal("50.00"), is_material=False))
        db.commit()

        pricing = get_or_create_project_pricing(db, project.id)
        pricing.hourly_rate_override = Decimal("600.00")
        pricing.fixed_total_price = Decimal("9000.00")
        pricing.rate_per_m2 = Decimal("200.00")
        pricing.rate_per_room = Decimal("3000.00")
        pricing.rate_per_piece = Decimal("1100.00")
        pricing.target_margin_pct = Decimal("30.00")
        pricing.include_materials = True
        pricing.include_travel_setup_buffers = True
        db.commit()
        return project.id
    finally:
        db.close()


def test_project_pricing_created_on_project_create():
    login(settings.admin_email, settings.admin_password)

    response = client.post(
        "/projects/new",
        data={"name": f"Pricing Project {uuid4().hex[:8]}", "status": "draft"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    project_id = int(location.rstrip("/").split("/")[-1])

    db = SessionLocal()
    try:
        pricing = db.query(ProjectPricing).filter(ProjectPricing.project_id == project_id).first()
        assert pricing is not None
        assert pricing.mode == "HOURLY"
    finally:
        db.close()


def test_pricing_validation_by_mode():
    db = SessionLocal()
    try:
        project = Project(name=f"Validation project {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        db.refresh(project)
        pricing = get_or_create_project_pricing(db, project.id)

        for mode, required_field in {
            "FIXED_TOTAL": "fixed_total_price",
            "PER_M2": "rate_per_m2",
            "PER_ROOM": "rate_per_room",
            "PIECEWORK": "rate_per_piece",
        }.items():
            payload = {
                "mode": mode,
                "include_materials": "on",
                "include_travel_setup_buffers": "on",
                "currency": "SEK",
            }
            try:
                update_project_pricing(db, pricing=pricing, payload=payload, user_id="admin@example.com")
                assert False, f"Expected PricingValidationError for mode {mode}"
            except PricingValidationError as exc:
                assert required_field in exc.errors

        assert "HOURLY" in PRICING_MODES
    finally:
        db.close()


def test_pricing_scenarios_values_golden():
    project_id = _make_golden_project()
    db = SessionLocal()
    try:
        baseline, scenarios = compute_pricing_scenarios(db, project_id)
    finally:
        db.close()

    assert baseline.labor_hours_total == Decimal("10.00")
    assert baseline.internal_total_cost == Decimal("3056.24")

    by_mode = {scenario.mode: scenario for scenario in scenarios}
    assert by_mode["HOURLY"].price_ex_vat == Decimal("6100.00")
    assert by_mode["FIXED_TOTAL"].price_ex_vat == Decimal("9000.00")
    assert by_mode["PER_M2"].price_ex_vat == Decimal("10000.00")
    assert by_mode["PER_ROOM"].price_ex_vat == Decimal("6000.00")
    assert by_mode["PIECEWORK"].price_ex_vat == Decimal("2200.00")


def test_per_m2_requires_units_warning():
    db = SessionLocal()
    try:
        project = Project(name=f"No m2 {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        pricing = get_or_create_project_pricing(db, project.id)
        pricing.mode = "PER_M2"
        pricing.rate_per_m2 = Decimal("50.00")
        db.commit()
        _, scenarios = compute_pricing_scenarios(db, project.id)
    finally:
        db.close()

    scenario = next(s for s in scenarios if s.mode == "PER_M2")
    assert scenario.invalid is True
    assert any("m²" in warning or "m2" in warning.lower() for warning in scenario.warnings)


def test_effective_hourly_computed():
    project_id = _make_golden_project()
    db = SessionLocal()
    try:
        _, scenarios = compute_pricing_scenarios(db, project_id)
    finally:
        db.close()
    hourly = next(s for s in scenarios if s.mode == "HOURLY")
    assert hourly.effective_hourly_sell_rate == Decimal("610.00")


def test_pricing_comparison_renders_table():
    login(settings.admin_email, settings.admin_password)
    project_id = _make_golden_project()
    page = client.get(f"/projects/{project_id}/pricing")
    assert page.status_code == 200
    assert "Сравнение режимов" in page.text
    assert "Use this mode" in page.text
    assert "Details" in page.text


def test_select_mode_persists():
    login(settings.admin_email, settings.admin_password)
    project_id = _make_golden_project()
    response = client.post(
        f"/projects/{project_id}/pricing",
        data={"intent": "select_mode", "selected_mode": "PER_ROOM"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        pricing = db.query(ProjectPricing).filter(ProjectPricing.project_id == project_id).first()
        assert pricing is not None
        assert pricing.mode == "PER_ROOM"
    finally:
        db.close()


def test_pricing_screen_persists_values_after_save():
    login(settings.admin_email, settings.admin_password)
    db = SessionLocal()
    try:
        project = Project(name=f"Persist pricing {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()

    save_response = client.post(
        f"/projects/{project_id}/pricing",
        data={
            "mode": "PIECEWORK",
            "rate_per_piece": "199.90",
            "target_margin_pct": "22.50",
            "include_materials": "on",
            "include_travel_setup_buffers": "on",
            "currency": "SEK",
        },
        follow_redirects=False,
    )
    assert save_response.status_code == 303

    page = client.get(f"/projects/{project_id}/pricing")
    assert page.status_code == 200
    assert 'value="PIECEWORK" checked' in page.text
    assert 'name="rate_per_piece" value="199.90"' in page.text
    assert 'name="target_margin_pct" value="22.50"' in page.text


def test_pricing_update_requires_role():
    ensure_user("pricing-viewer@example.com", "viewer")
    login("pricing-viewer@example.com", "test-password")

    db = SessionLocal()
    try:
        project = Project(name=f"RBAC pricing {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/pricing",
        data={"mode": "HOURLY", "currency": "SEK"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_pricing_post_requires_csrf():
    login(settings.admin_email, settings.admin_password)
    db = SessionLocal()
    try:
        project = Project(name=f"CSRF pricing {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/pricing",
        data={"mode": "HOURLY", "currency": "SEK"},
        headers={"X-No-Auto-CSRF": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_pricing_ui_no_nan_or_negative_zero():
    login(settings.admin_email, settings.admin_password)
    project_id = _make_golden_project()
    page = client.get(f"/projects/{project_id}/pricing")
    assert page.status_code == 200
    assert "NaN" not in page.text
    assert "Infinity" not in page.text
    assert "-0.00" not in page.text


def test_warnings_for_missing_units():
    db = SessionLocal()
    try:
        project = Project(name=f"Warnings project {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        pricing = get_or_create_project_pricing(db, project.id)
        pricing.rate_per_m2 = Decimal("100.00")
        pricing.rate_per_room = Decimal("1000.00")
        pricing.rate_per_piece = Decimal("99.00")
        db.commit()
        _, scenarios = compute_pricing_scenarios(db, project.id)
    finally:
        db.close()

    by_mode = {scenario.mode: scenario for scenario in scenarios}
    assert WARNING_MISSING_UNITS_M2 in by_mode["PER_M2"].warnings
    assert WARNING_MISSING_UNITS_ROOMS in by_mode["PER_ROOM"].warnings
    assert WARNING_MISSING_ITEMS in by_mode["PIECEWORK"].warnings


def test_use_this_mode_persists_and_prefills():
    login(settings.admin_email, settings.admin_password)
    project_id = _make_golden_project()
    response = client.post(
        f"/projects/{project_id}/pricing",
        data={"intent": "select_mode", "selected_mode": "PER_M2"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        pricing = db.query(ProjectPricing).filter(ProjectPricing.project_id == project_id).first()
        assert pricing is not None
        assert pricing.mode == "PER_M2"
        assert pricing.rate_per_m2 == Decimal("200.00")
    finally:
        db.close()

    page = client.get(f"/projects/{project_id}/pricing")
    assert page.status_code == 200
    assert 'value="PER_M2" checked' in page.text
    assert 'name="rate_per_m2" value="200.00"' in page.text


def test_details_section_contains_baseline_and_formula():
    login(settings.admin_email, settings.admin_password)
    project_id = _make_golden_project()
    page = client.get(f"/projects/{project_id}/pricing")
    assert page.status_code == 200
    assert "Formula:" in page.text
    assert "Baseline breakdown:" in page.text
    assert "Include flags:" in page.text


def test_double_click_guard():
    login(settings.admin_email, settings.admin_password)
    project_id = _make_golden_project()
    page = client.get(f"/projects/{project_id}/pricing")
    assert page.status_code == 200
    assert "js-mode-select-btn" in page.text
    assert "btn.disabled = true;" in page.text
    assert "Saving..." in page.text


def test_conversion_golden_desired_hourly_and_margin_formula():
    project_id = _make_golden_project()
    db = SessionLocal()
    try:
        conversion = compute_conversions(
            db,
            project_id,
            DesiredInput(desired_effective_hourly_ex_vat=Decimal("650.00")),
        )
        assert conversion.implied_fixed_total_price == Decimal("6500.00")
        assert conversion.implied_rate_per_m2 == Decimal("130.00")

        margin_conversion = compute_conversions(
            db,
            project_id,
            DesiredInput(desired_margin_pct=Decimal("20.00")),
        )
        baseline = compute_project_baseline(
            db,
            project_id,
            include_materials=True,
            include_travel_setup_buffers=True,
        )
        expected_price = (baseline.internal_total_cost / Decimal("0.80")).quantize(Decimal("0.01"))
        assert margin_conversion.implied_fixed_total_price == expected_price
    finally:
        db.close()


def test_converter_panel_renders():
    login(settings.admin_email, settings.admin_password)
    project_id = _make_golden_project()
    page = client.get(f"/projects/{project_id}/pricing")
    assert page.status_code == 200
    assert "Конвертер" in page.text
    assert "Desired effective hourly (ex VAT)" in page.text
    assert "Apply to Fixed" not in page.text


def test_apply_conversion_updates_project_pricing():
    login(settings.admin_email, settings.admin_password)
    project_id = _make_golden_project()

    calculate_response = client.post(
        f"/projects/{project_id}/pricing",
        data={"intent": "calculate_conversion", "desired_effective_hourly_ex_vat": "700.00"},
        follow_redirects=False,
    )
    assert calculate_response.status_code == 200
    assert "Apply to m²" in calculate_response.text

    apply_response = client.post(
        f"/projects/{project_id}/pricing",
        data={"intent": "apply_conversion", "apply_mode": "PER_M2", "apply_value": "140.00"},
        follow_redirects=False,
    )
    assert apply_response.status_code == 303

    db = SessionLocal()
    try:
        pricing = db.query(ProjectPricing).filter(ProjectPricing.project_id == project_id).first()
        assert pricing is not None
        assert pricing.rate_per_m2 == Decimal("140.00")
    finally:
        db.close()


def test_converter_warns_when_m2_zero():
    db = SessionLocal()
    try:
        project = Project(name=f"Conv warn m2 {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        conversion = compute_conversions(
            db,
            project.id,
            DesiredInput(desired_effective_hourly_ex_vat=Decimal("650.00")),
        )
        assert WARNING_MISSING_UNITS_M2 in conversion.warnings
    finally:
        db.close()


def test_converter_warns_when_hours_zero():
    db = SessionLocal()
    try:
        project = Project(name=f"Conv warn hours {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        conversion = compute_conversions(
            db,
            project.id,
            DesiredInput(fixed_total_price=Decimal("1000.00")),
        )
        assert WARNING_MISSING_BASELINE in conversion.warnings
    finally:
        db.close()


def test_floor_recommended_price_max_of_constraints():
    db = SessionLocal()
    try:
        project_id = _make_golden_project()
        policy = PricingPolicy(
            min_margin_pct=Decimal("15.00"),
            min_profit_sek=Decimal("1000.00"),
            min_effective_hourly_ex_vat=Decimal("700.00"),
        )
        db.add(policy)
        db.commit()
        baseline, scenarios = compute_pricing_scenarios(db, project_id)
        scenario = next(sc for sc in scenarios if sc.mode == "HOURLY")
        result = evaluate_floor(baseline, scenario, policy)

        c_profit = (baseline.internal_total_cost + Decimal("1000.00")).quantize(Decimal("0.01"))
        c_margin = (baseline.internal_total_cost / Decimal("0.85")).quantize(Decimal("0.01"))
        c_hourly = (Decimal("700.00") * baseline.labor_hours_total).quantize(Decimal("0.01"))
        assert result.recommended_min_price_ex_vat == max(c_profit, c_margin, c_hourly)
    finally:
        db.close()


def test_floor_below_when_negative_profit():
    db = SessionLocal()
    try:
        project_id = _make_golden_project()
        pricing = get_or_create_project_pricing(db, project_id)
        pricing.fixed_total_price = Decimal("1.00")
        pricing.mode = "FIXED_TOTAL"
        db.add(pricing)
        db.commit()

        baseline, scenarios = compute_pricing_scenarios(db, project_id)
        scenario = next(sc for sc in scenarios if sc.mode == "FIXED_TOTAL")
        policy = PricingPolicy(min_margin_pct=Decimal("10.00"), min_profit_sek=Decimal("0.00"), min_effective_hourly_ex_vat=Decimal("1.00"))
        result = evaluate_floor(baseline, scenario, policy)
        reason_codes = {reason.code for reason in result.reasons}
        assert result.is_below_floor is True
        assert "NEGATIVE_PROFIT" in reason_codes
    finally:
        db.close()


def test_pricing_ui_shows_below_floor_badge_and_recommendations():
    login(settings.admin_email, settings.admin_password)
    project_id = _make_golden_project()

    db = SessionLocal()
    try:
        pricing = get_or_create_project_pricing(db, project_id)
        pricing.mode = "FIXED_TOTAL"
        pricing.fixed_total_price = Decimal("1.00")
        db.add(pricing)

        policy = db.query(PricingPolicy).first()
        if not policy:
            policy = PricingPolicy()
        policy.min_margin_pct = Decimal("50.00")
        policy.min_profit_sek = Decimal("5000.00")
        policy.min_effective_hourly_ex_vat = Decimal("900.00")
        db.add(policy)
        db.commit()
    finally:
        db.close()

    page = client.get(f"/projects/{project_id}/pricing")
    assert page.status_code == 200
    assert "BELOW FLOOR" in page.text
    assert "Recommended minimum" in page.text
    assert "Apply recommended values" in page.text
