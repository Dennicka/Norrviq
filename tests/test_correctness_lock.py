from decimal import Decimal

from app.models.project import Project, ProjectWorkItem
from app.services.correctness_lock import validate_estimate_invariants


def test_correctness_lock_detects_negative_values():
    project = Project(work_sum_without_moms=Decimal('0'), materials_cost=Decimal('0'), total_cost=Decimal('0'))
    item_hours = ProjectWorkItem(quantity=Decimal('-2'), calculated_hours=Decimal('-1'))
    project.work_items = [item_hours]
    result = validate_estimate_invariants(project)
    assert not result.ok
    codes = {e['code'] for e in result.errors}
    assert 'ESTIMATE_NEGATIVE_TOTAL' in codes
    assert 'ESTIMATE_NEGATIVE_QUANTITY' in codes
