from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models.buffer_rule import BufferRule
from app.models.cost import CostCategory
from app.models.project import Project
from app.models.worktype import WorkType
from app.services.buffer_rules import resolve_effective_buffer

router = APIRouter(prefix="/api/ui/buffer-rules", tags=["buffer_rules_api"])

ALLOWED_SCOPE_TYPES = {"GLOBAL", "PROJECT", "WORKTYPE", "CATEGORY"}
ALLOWED_KINDS = {"SETUP", "CLEANUP", "TRAVEL", "RISK"}
ALLOWED_BASIS = {"LABOR_HOURS", "INTERNAL_COST"}
ALLOWED_UNITS = {"PERCENT", "FIXED_HOURS", "FIXED_SEK"}


class BufferRulePayload(BaseModel):
    kind: str
    basis: str
    unit: str
    value: Decimal
    scope_type: str
    scope_id: int | None = None
    priority: int = 0
    is_active: bool = True


class BufferRuleView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    basis: str
    unit: str
    value: Decimal
    scope_type: str
    scope_id: int | None
    priority: int
    is_active: bool


class BufferRulesListResponse(BaseModel):
    total: int
    items: list[BufferRuleView]


def _validate_value(value: Decimal, unit: str) -> Decimal:
    try:
        normalized = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        raise HTTPException(status_code=400, detail="Invalid value")
    if unit == "PERCENT" and (normalized < Decimal("0") or normalized > Decimal("100")):
        raise HTTPException(status_code=400, detail="PERCENT value must be between 0 and 100")
    return normalized


def _validate_scope(db: Session, scope_type: str, scope_id: int | None):
    if scope_type == "GLOBAL":
        if scope_id is not None:
            raise HTTPException(status_code=400, detail="GLOBAL rule must not have scope_id")
        return
    if scope_id is None:
        raise HTTPException(status_code=400, detail="Non-global rule requires scope_id")
    if scope_type == "PROJECT" and db.get(Project, scope_id) is None:
        raise HTTPException(status_code=404, detail="Project scope target not found")
    if scope_type == "WORKTYPE" and db.get(WorkType, scope_id) is None:
        raise HTTPException(status_code=404, detail="WorkType scope target not found")
    if scope_type == "CATEGORY" and db.get(CostCategory, scope_id) is None:
        raise HTTPException(status_code=404, detail="Category scope target not found")


@router.get("", response_model=BufferRulesListResponse)
def list_buffer_rules(
    project_id: int | None = None,
    active: bool | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(BufferRule)
    if active is not None:
        query = query.filter(BufferRule.is_active.is_(active))
    if project_id is not None:
        query = query.filter(BufferRule.scope_type == "PROJECT", BufferRule.scope_id == project_id)

    total = query.count()
    items = query.order_by(BufferRule.created_at.desc(), BufferRule.id.desc()).offset(offset).limit(limit).all()
    return BufferRulesListResponse(total=total, items=items)


@router.post("", response_model=BufferRuleView, status_code=status.HTTP_201_CREATED)
def create_buffer_rule(payload: BufferRulePayload, db: Session = Depends(get_db)):
    kind = payload.kind.upper()
    basis = payload.basis.upper()
    unit = payload.unit.upper()
    scope_type = payload.scope_type.upper()

    if kind not in ALLOWED_KINDS or basis not in ALLOWED_BASIS or unit not in ALLOWED_UNITS or scope_type not in ALLOWED_SCOPE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid kind/basis/unit/scope_type")
    _validate_scope(db, scope_type, payload.scope_id)
    value = _validate_value(payload.value, unit)

    if unit == "FIXED_HOURS" and basis != "LABOR_HOURS":
        raise HTTPException(status_code=400, detail="FIXED_HOURS requires LABOR_HOURS basis")
    if unit == "FIXED_SEK" and basis != "INTERNAL_COST":
        raise HTTPException(status_code=400, detail="FIXED_SEK requires INTERNAL_COST basis")

    rule = BufferRule(
        kind=kind,
        basis=basis,
        unit=unit,
        value=value,
        scope_type=scope_type,
        scope_id=payload.scope_id,
        priority=payload.priority,
        is_active=payload.is_active,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/{rule_id}", response_model=BufferRuleView)
def update_buffer_rule(rule_id: int, payload: BufferRulePayload, db: Session = Depends(get_db)):
    rule = db.get(BufferRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    kind = payload.kind.upper()
    basis = payload.basis.upper()
    unit = payload.unit.upper()
    scope_type = payload.scope_type.upper()
    if kind not in ALLOWED_KINDS or basis not in ALLOWED_BASIS or unit not in ALLOWED_UNITS or scope_type not in ALLOWED_SCOPE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid kind/basis/unit/scope_type")
    _validate_scope(db, scope_type, payload.scope_id)
    value = _validate_value(payload.value, unit)

    rule.kind = kind
    rule.basis = basis
    rule.unit = unit
    rule.value = value
    rule.scope_type = scope_type
    rule.scope_id = payload.scope_id
    rule.priority = payload.priority
    rule.is_active = payload.is_active
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.put("/{rule_id}", response_model=BufferRuleView)
def put_buffer_rule(rule_id: int, payload: BufferRulePayload, db: Session = Depends(get_db)):
    return update_buffer_rule(rule_id, payload, db)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_buffer_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(BufferRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()


@router.get("/effective")
def effective_buffer(project_id: int, worktype_id: int | None = None, db: Session = Depends(get_db)):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if worktype_id is not None and db.get(WorkType, worktype_id) is None:
        raise HTTPException(status_code=404, detail="WorkType not found")

    resolved = resolve_effective_buffer(db, project_id=project_id, worktype_id=worktype_id)
    return {
        "applied_rule_id": resolved.applied_rule_id,
        "scope": resolved.scope,
        "buffer_value": str(resolved.buffer_value) if resolved.buffer_value is not None else None,
        "buffer_unit": resolved.buffer_unit,
        "buffer_basis": resolved.buffer_basis,
        "reason": resolved.reason,
    }
