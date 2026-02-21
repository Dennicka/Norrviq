from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.buffer_rule import BufferRule


@dataclass
class EffectiveBufferResult:
    applied_rule_id: int | None
    scope: str | None
    buffer_value: Decimal | None
    buffer_unit: str | None
    buffer_basis: str | None
    reason: str


def resolve_effective_buffer(
    session: Session,
    project_id: int,
    worktype_id: int | None = None,
    at_time: datetime | None = None,
) -> EffectiveBufferResult:
    """Resolve one effective buffer rule for a project deterministically.

    Selection contract (locked for regression safety):
    1. Eligible rules are only active ones (`is_active = True`).
    2. Scope precedence is most specific first: WORKTYPE (if `worktype_id` provided)
       -> PROJECT -> GLOBAL.
    3. Inside a scope, higher `priority` wins.
    4. Tie-break inside a scope with same priority: newest `created_at` wins.
    5. Final tie-break if timestamps are equal: lowest `id` wins.

    `at_time` is accepted for forward compatibility but currently not used because
    the model has no temporal validity fields.
    """

    del at_time

    rules = session.query(BufferRule).filter(BufferRule.is_active.is_(True)).all()

    candidates: list[tuple[int, str, BufferRule]] = []
    if worktype_id is not None:
        for rule in rules:
            if rule.scope_type == "WORKTYPE" and rule.scope_id == worktype_id:
                candidates.append((0, "worktype", rule))
    for rule in rules:
        if rule.scope_type == "PROJECT" and rule.scope_id == project_id:
            candidates.append((1, "project", rule))
        elif rule.scope_type == "GLOBAL":
            candidates.append((2, "global", rule))

    if not candidates:
        return EffectiveBufferResult(
            applied_rule_id=None,
            scope=None,
            buffer_value=None,
            buffer_unit=None,
            buffer_basis=None,
            reason="No eligible active rules matched scope",
        )

    selected_scope_rank, selected_scope_name, selected_rule = min(
        candidates,
        key=lambda item: (
            item[0],
            -int(item[2].priority or 0),
            -(item[2].created_at.timestamp() if item[2].created_at else 0.0),
            int(item[2].id),
        ),
    )

    del selected_scope_rank

    return EffectiveBufferResult(
        applied_rule_id=selected_rule.id,
        scope=selected_scope_name,
        buffer_value=Decimal(str(selected_rule.value)),
        buffer_unit=selected_rule.unit,
        buffer_basis=selected_rule.basis,
        reason=(
            f"matched by {selected_rule.scope_type} scope, highest priority, "
            "newest created_at, then lowest id"
        ),
    )
