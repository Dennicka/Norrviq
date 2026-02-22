import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.audit_log import AuditLog
from app.security import require_role

router = APIRouter(prefix="/admin/audit", tags=["audit"])
MAX_EXPORT_ROWS = 50000


def _apply_filters(query, request: Request):
    params = request.query_params
    if params.get("action"):
        query = query.filter(AuditLog.action == params["action"])
    if params.get("entity_type"):
        query = query.filter(AuditLog.entity_type == params["entity_type"])
    if params.get("entity_id"):
        query = query.filter(AuditLog.entity_id == params["entity_id"])
    if params.get("actor_user_id"):
        query = query.filter(AuditLog.actor_user_id == int(params["actor_user_id"]))
    if params.get("severity"):
        query = query.filter(AuditLog.severity == params["severity"])
    return query


@router.get("")
async def audit_viewer(
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role("admin", "auditor")),
):
    page = max(int(request.query_params.get("page", "1")), 1)
    page_size = 50
    query = _apply_filters(db.query(AuditLog), request)
    total = query.count()
    rows = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    context = template_context(request, lang)
    context.update({"rows": rows, "total": total, "page": page, "page_size": page_size})
    return templates.TemplateResponse(request, "admin/audit.html", context)


def _fetch_for_export(db: Session, request: Request):
    query = _apply_filters(db.query(AuditLog), request).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    count = query.count()
    if count > MAX_EXPORT_ROWS:
        raise HTTPException(status_code=400, detail=f"Export too large ({count}), max is {MAX_EXPORT_ROWS}")
    return query


@router.get("/export.json")
async def export_json(request: Request, db: Session = Depends(get_db), _role: str = Depends(require_role("admin", "auditor"))):
    query = _fetch_for_export(db, request)

    def _iter():
        yield "["
        first = True
        for row in query.yield_per(500):
            payload = {
                "id": row.id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "actor_user_id": row.actor_user_id,
                "actor_role": row.actor_role,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "request_id": row.request_id,
                "ip_address": row.ip_address,
                "user_agent": row.user_agent,
                "severity": row.severity.value,
                "metadata": json.loads(row.metadata_json or "{}"),
                "hash": row.hash,
                "prev_hash": row.prev_hash,
            }
            if not first:
                yield ","
            first = False
            yield json.dumps(payload, ensure_ascii=False)
        yield "]"

    return StreamingResponse(_iter(), media_type="application/json")


@router.get("/export.csv")
async def export_csv(request: Request, db: Session = Depends(get_db), _role: str = Depends(require_role("admin", "auditor"))):
    query = _fetch_for_export(db, request)

    def _iter():
        header = ["id", "created_at", "actor_user_id", "actor_role", "action", "entity_type", "entity_id", "request_id", "ip_address", "user_agent", "severity", "metadata_json", "hash", "prev_hash"]
        s = io.StringIO()
        w = csv.writer(s)
        w.writerow(header)
        yield s.getvalue()
        s.seek(0)
        s.truncate(0)
        for row in query.yield_per(500):
            w.writerow([row.id, row.created_at.isoformat() if row.created_at else "", row.actor_user_id or "", row.actor_role or "", row.action, row.entity_type or "", row.entity_id or "", row.request_id or "", row.ip_address or "", row.user_agent or "", row.severity.value, row.metadata_json, row.hash, row.prev_hash or ""])
            yield s.getvalue()
            s.seek(0)
        s.truncate(0)

    return StreamingResponse(_iter(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=audit_log.csv"})
