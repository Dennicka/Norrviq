import os
import time
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.config import get_settings
from app.db import SessionLocal, engine
from app.main import app
from app.models.invoice import Invoice
from app.models.pricing_policy import get_or_create_pricing_policy
from app.services.completeness import compute_completeness
from app.services.large_project import LargeProjectSpec, create_large_project
from app.services.pricing import compute_pricing_scenarios, evaluate_floor
from app.services.quality import evaluate_project_quality

RUN_PERF_TESTS = os.getenv("RUN_PERF_TESTS", "").lower() in {"1", "true", "yes"}

pytestmark = [
    pytest.mark.perf,
    pytest.mark.skipif(not RUN_PERF_TESTS, reason="RUN_PERF_TESTS is not enabled"),
]

BASELINE_THRESHOLD_S = 2.0
PRICING_THRESHOLD_S = 2.0
PIPELINE_THRESHOLD_S = 6.0
HTTP_THRESHOLD_S = 3.0
QUERY_THRESHOLD = 2000

client = TestClient(app)
settings = get_settings()


def _login_admin() -> None:
    response = client.post(
        "/login",
        data={"username": settings.admin_email, "password": settings.admin_password, "next": "/projects/"},
        follow_redirects=False,
    )
    assert response.status_code in {302, 303}


@contextmanager
def _count_queries():
    count = {"value": 0}

    def before_cursor_execute(*_args, **_kwargs):
        count["value"] += 1

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield count
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


def _build_large_project() -> int:
    db = SessionLocal()
    try:
        project = create_large_project(
            db,
            spec=LargeProjectSpec(rooms_count=50, work_items_count=300),
            name=f"Perf Project {uuid4().hex[:8]}",
        )
        return project.id
    finally:
        db.close()


def test_large_project_pipeline_performance():
    project_id = _build_large_project()

    db = SessionLocal()
    try:
        with _count_queries() as query_count:
            pipeline_started = time.perf_counter()

            baseline_started = time.perf_counter()
            baseline, scenarios = compute_pricing_scenarios(db, project_id)
            baseline_elapsed = time.perf_counter() - baseline_started

            pricing_started = time.perf_counter()
            _baseline_again, scenarios_again = compute_pricing_scenarios(db, project_id)
            pricing_elapsed = time.perf_counter() - pricing_started

            policy = get_or_create_pricing_policy(db)
            floor_started = time.perf_counter()
            _floor_results = [evaluate_floor(baseline, scenario, policy) for scenario in scenarios]
            floor_elapsed = time.perf_counter() - floor_started

            completeness_started = time.perf_counter()
            _completeness = compute_completeness(db, project_id, mode="HOURLY", segment="ANY")
            completeness_elapsed = time.perf_counter() - completeness_started

            quality_started = time.perf_counter()
            _quality = evaluate_project_quality(db, project_id, lang="ru")
            quality_elapsed = time.perf_counter() - quality_started

            pipeline_elapsed = time.perf_counter() - pipeline_started

        print(
            "PERF pipeline timings "
            f"baseline={baseline_elapsed:.3f}s pricing={pricing_elapsed:.3f}s floor={floor_elapsed:.3f}s "
            f"completeness={completeness_elapsed:.3f}s quality={quality_elapsed:.3f}s "
            f"total={pipeline_elapsed:.3f}s queries={query_count['value']}"
        )

        assert len(scenarios_again) >= 5
        assert baseline_elapsed < BASELINE_THRESHOLD_S
        assert pricing_elapsed < PRICING_THRESHOLD_S
        assert pipeline_elapsed < PIPELINE_THRESHOLD_S
        assert query_count["value"] <= QUERY_THRESHOLD
    finally:
        db.close()


def test_large_project_ui_stress_safety():
    _login_admin()
    project_id = _build_large_project()

    timings = {}

    project_started = time.perf_counter()
    project_response = client.get(f"/projects/{project_id}")
    timings["project"] = time.perf_counter() - project_started

    pricing_started = time.perf_counter()
    pricing_response = client.get(f"/projects/{project_id}/pricing")
    timings["pricing"] = time.perf_counter() - pricing_started

    create_invoice_response = client.post(
        f"/projects/{project_id}/invoices/create-from-project",
        data={"include_labor": "true", "include_materials": "true", "merge_strategy": "REPLACE_ALL"},
        follow_redirects=False,
    )
    assert create_invoice_response.status_code in {302, 303}

    db = SessionLocal()
    try:
        invoice = (
            db.query(Invoice)
            .filter(Invoice.project_id == project_id, Invoice.status == "draft")
            .order_by(Invoice.id.desc())
            .first()
        )
        assert invoice is not None
        invoice_id = invoice.id
    finally:
        db.close()

    invoice_started = time.perf_counter()
    invoice_response = client.get(f"/projects/{project_id}/invoices/{invoice_id}")
    timings["invoice"] = time.perf_counter() - invoice_started

    print(
        "PERF ui timings "
        f"project={timings['project']:.3f}s pricing={timings['pricing']:.3f}s invoice={timings['invoice']:.3f}s"
    )

    for response in (project_response, pricing_response, invoice_response):
        assert response.status_code == 200
        assert len(response.text) < 5_000_000
    for elapsed in timings.values():
        assert elapsed < HTTP_THRESHOLD_S
