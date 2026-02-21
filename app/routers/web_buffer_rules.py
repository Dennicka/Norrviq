import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.audit_event import AuditEvent
from app.models.buffer_rule import BufferRule
from app.models.project import Project
from app.models.worktype import WorkType
from app.security import get_current_user_email
from app.services.buffer_audit import log_buffer_audit
from app.services.buffer_rules import resolve_effective_buffer

router = APIRouter(prefix="/web/buffer-rules", tags=["web_buffer_rules"])

ALLOWED_SCOPE_TYPES = {"GLOBAL", "PROJECT", "WORKTYPE"}
ALLOWED_KINDS = {"SETUP", "CLEANUP", "TRAVEL", "RISK"}
ALLOWED_BASIS = {"LABOR_HOURS", "INTERNAL_COST"}
ALLOWED_UNITS = {"PERCENT", "FIXED_HOURS", "FIXED_SEK"}


def _rule_to_dict(rule: BufferRule) -> dict:
    return {
        "id": rule.id,
        "kind": rule.kind,
        "basis": rule.basis,
        "unit": rule.unit,
        "value": str(rule.value),
        "scope_type": rule.scope_type,
        "scope_id": rule.scope_id,
        "priority": rule.priority,
        "is_active": rule.is_active,
    }


def _parse_rule_form(data: dict, db: Session) -> tuple[dict, dict]:
    errors: dict[str, str] = {}
    parsed: dict = {}

    kind = (data.get("kind") or "").strip().upper()
    basis = (data.get("basis") or "").strip().upper()
    unit = (data.get("unit") or "").strip().upper()
    scope_type = (data.get("scope_type") or "").strip().upper()

    if kind not in ALLOWED_KINDS:
        errors["kind"] = "Invalid kind"
    if basis not in ALLOWED_BASIS:
        errors["basis"] = "Invalid basis"
    if unit not in ALLOWED_UNITS:
        errors["unit"] = "Invalid unit"
    if scope_type not in ALLOWED_SCOPE_TYPES:
        errors["scope_type"] = "Invalid scope"

    parsed.update({"kind": kind, "basis": basis, "unit": unit, "scope_type": scope_type})

    value_raw = (data.get("value") or "").strip()
    try:
        value = Decimal(value_raw).quantize(Decimal("0.01"))
        if unit == "PERCENT" and (value < Decimal("0") or value > Decimal("100")):
            errors["value"] = "Percent must be between 0 and 100"
    except (InvalidOperation, ValueError):
        errors["value"] = "Invalid numeric value"
        value = Decimal("0.00")
    parsed["value"] = value

    priority_raw = (data.get("priority") or "0").strip()
    try:
        parsed["priority"] = int(priority_raw)
    except ValueError:
        errors["priority"] = "Priority must be integer"
        parsed["priority"] = 0

    parsed["is_active"] = data.get("is_active") in ("on", "true", "1", True, 1)

    scope_id_raw = (data.get("scope_id") or "").strip()
    if scope_type == "GLOBAL":
        parsed["scope_id"] = None
    else:
        if not scope_id_raw.isdigit():
            errors["scope_id"] = "Scope ID is required"
            parsed["scope_id"] = None
        else:
            parsed["scope_id"] = int(scope_id_raw)
            if scope_type == "PROJECT" and db.get(Project, parsed["scope_id"]) is None:
                errors["scope_id"] = "Project not found"
            if scope_type == "WORKTYPE" and db.get(WorkType, parsed["scope_id"]) is None:
                errors["scope_id"] = "Worktype not found"

    if unit == "FIXED_HOURS" and basis != "LABOR_HOURS":
        errors["unit"] = "FIXED_HOURS requires LABOR_HOURS"
    if unit == "FIXED_SEK" and basis != "INTERNAL_COST":
        errors["unit"] = "FIXED_SEK requires INTERNAL_COST"

    return parsed, errors


def _load_history(db: Session, *, project_id: int | None, rule_id: int | None, limit: int = 50) -> list[dict]:
    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.entity_type.in_(["buffer_rule", "project_buffer_settings"]))
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit * 3)
        .all()
    )
    rows = []
    for event in events:
        details = {}
        if event.details:
            try:
                details = json.loads(event.details)
            except json.JSONDecodeError:
                details = {}
        if rule_id is not None and not (
            event.entity_type == "buffer_rule" and event.entity_id == rule_id
        ):
            continue
        if project_id is not None:
            is_project_event = event.entity_type == "project_buffer_settings" and event.entity_id == project_id
            after_json = details.get("after_json") or {}
            before_json = details.get("before_json") or {}
            is_rule_for_project = (
                event.entity_type == "buffer_rule"
                and (
                    (after_json.get("scope_type") == "PROJECT" and after_json.get("scope_id") == project_id)
                    or (before_json.get("scope_type") == "PROJECT" and before_json.get("scope_id") == project_id)
                )
            )
            if not (is_project_event or is_rule_for_project):
                continue
        rows.append({"event": event, "details": details})
        if len(rows) >= limit:
            break
    return rows


@router.get("")
async def buffer_rules_page(
    request: Request,
    project_id: int | None = None,
    active: str = "all",
    scope: str = "all",
    rule_id: int | None = None,
    q: str = "",
    edit_rule_id: int | None = None,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    query = db.query(BufferRule)
    if project_id is not None:
        query = query.filter(BufferRule.scope_type == "PROJECT", BufferRule.scope_id == project_id)
    if active in {"true", "false"}:
        query = query.filter(BufferRule.is_active.is_(active == "true"))
    if scope in ALLOWED_SCOPE_TYPES:
        query = query.filter(BufferRule.scope_type == scope)
    if rule_id is not None:
        query = query.filter(BufferRule.id == rule_id)
    rules = query.order_by(BufferRule.priority.desc(), BufferRule.id.desc()).all()

    if q:
        q_l = q.lower()
        rules = [r for r in rules if q_l in str(r.id) or q_l in r.kind.lower() or q_l in r.scope_type.lower()]

    form_data = {}
    if edit_rule_id is not None:
        edit_rule = db.get(BufferRule, edit_rule_id)
        if edit_rule:
            form_data = {
                "rule_id": str(edit_rule.id),
                "kind": edit_rule.kind,
                "basis": edit_rule.basis,
                "unit": edit_rule.unit,
                "value": str(edit_rule.value),
                "scope_type": edit_rule.scope_type,
                "scope_id": str(edit_rule.scope_id or ""),
                "priority": str(edit_rule.priority),
                "is_active": "on" if edit_rule.is_active else "",
            }

    projects = db.query(Project).order_by(Project.name.asc()).all()
    worktypes = db.query(WorkType).order_by(WorkType.name_sv.asc().nullslast(), WorkType.id.asc()).all()
    history_rows = _load_history(db, project_id=project_id, rule_id=rule_id)

    context = template_context(request, lang)
    context.update(
        {
            "rules": rules,
            "projects": projects,
            "worktypes": worktypes,
            "filters": {"project_id": project_id, "active": active, "scope": scope, "rule_id": rule_id, "q": q},
            "form_data": form_data,
            "errors": {},
            "history_rows": history_rows,
        }
    )
    return templates.TemplateResponse("buffer_rules.html", context)


@router.post("")
async def create_or_update_rule(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    form = await request.form()
    data = dict(form)
    parsed, errors = _parse_rule_form(data, db)
    rule_id = data.get("rule_id")
    is_update = bool(rule_id)

    if is_update:
        rule = db.get(BufferRule, int(rule_id))
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")
    else:
        rule = BufferRule()

    if errors:
        projects = db.query(Project).order_by(Project.name.asc()).all()
        worktypes = db.query(WorkType).order_by(WorkType.name_sv.asc().nullslast(), WorkType.id.asc()).all()
        context = template_context(request, lang)
        context.update(
            {
                "rules": db.query(BufferRule).order_by(BufferRule.priority.desc(), BufferRule.id.desc()).all(),
                "projects": projects,
                "worktypes": worktypes,
                "filters": {"project_id": None, "active": "all", "scope": "all", "rule_id": None, "q": ""},
                "form_data": data,
                "errors": errors,
                "history_rows": _load_history(db, project_id=None, rule_id=None),
            }
        )
        return templates.TemplateResponse("buffer_rules.html", context, status_code=400)

    before = _rule_to_dict(rule) if is_update else None
    rule.kind = parsed["kind"]
    rule.basis = parsed["basis"]
    rule.unit = parsed["unit"]
    rule.value = parsed["value"]
    rule.scope_type = parsed["scope_type"]
    rule.scope_id = parsed["scope_id"]
    rule.priority = parsed["priority"]
    rule.is_active = parsed["is_active"]
    db.add(rule)
    db.flush()

    log_buffer_audit(
        db,
        actor=get_current_user_email(request) or "system",
        action="UPDATE" if is_update else "CREATE",
        entity_type="buffer_rule",
        entity_id=rule.id,
        before=before,
        after=_rule_to_dict(rule),
        request_id=getattr(request.state, "request_id", None),
    )
    db.commit()
    return RedirectResponse(url="/web/buffer-rules", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{rule_id}/delete")
async def delete_rule(rule_id: int, request: Request, db: Session = Depends(get_db)):
    rule = db.get(BufferRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    before = _rule_to_dict(rule)
    db.delete(rule)
    log_buffer_audit(
        db,
        actor=get_current_user_email(request) or "system",
        action="DELETE",
        entity_type="buffer_rule",
        entity_id=rule_id,
        before=before,
        after=None,
        request_id=getattr(request.state, "request_id", None),
    )
    db.commit()
    return RedirectResponse(url="/web/buffer-rules", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/effective")
async def effective_preview(project_id: int, worktype_id: int | None = None, db: Session = Depends(get_db)):
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
