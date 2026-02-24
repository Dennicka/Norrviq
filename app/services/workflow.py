from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session, selectinload

from app.models.audit_event import AuditEvent
from app.models.company_profile import get_or_create_company_profile
from app.models.pricing_policy import get_or_create_pricing_policy
from app.models.project import Project
from app.services.completeness import compute_completeness
from app.services.material_norms import build_project_material_bom
from app.services.pricing import compute_pricing_scenarios
from app.services.project_pricing import build_project_pricing_summary
from app.services.quality import evaluate_project_quality


@dataclass
class WorkflowStep:
    key: str
    title_key: str
    status: str
    messages: list[str]
    cta_url: str | None = None


def _invoice_status(project: Project) -> str:
    invoices = sorted(project.invoices, key=lambda inv: inv.id)
    if any(inv.status == "issued" for inv in invoices):
        return "issued"
    if any(inv.status == "draft" for inv in invoices):
        return "draft"
    return "none"


def _offer_status(project: Project) -> str:
    if project.offer_number and project.offer_status == "issued":
        return "issued"
    if project.offer_commercial_snapshot or project.offer_status == "draft":
        return "draft"
    return "none"


def build_project_workflow_state(db: Session, project_id: int, *, lang: str = "ru") -> dict:
    project = (
        db.query(Project)
        .options(
            selectinload(Project.client),
            selectinload(Project.rooms),
            selectinload(Project.work_items),
            selectinload(Project.pricing),
            selectinload(Project.invoices),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise ValueError("Project not found")

    pricing = project.pricing
    pricing_mode = (pricing.mode if pricing else None) or ""
    pricing_summary = build_project_pricing_summary(project, db)
    bom_report = build_project_material_bom(project.id, db)
    quality_report = evaluate_project_quality(db, project.id, lang=lang)
    segment = project.client.client_segment if project.client and project.client.client_segment else "ANY"
    completeness = compute_completeness(db, project.id, mode=pricing_mode or "HOURLY", segment=segment, lang=lang)
    _baseline, scenarios = compute_pricing_scenarios(db, project.id)
    selected_scenario = next((s for s in scenarios if s.mode == (pricing_mode or "HOURLY")), None)

    step1_messages: list[str] = []
    step1_status = "done"
    if not (project.name or "").strip():
        step1_status = "blocked"
        step1_messages.append("workflow.msg.project_name_required")
    if not project.client_id:
        step1_status = "warning" if step1_status != "blocked" else step1_status
        step1_messages.append("workflow.msg.client_missing")

    step2_messages: list[str] = []
    if len(project.rooms) == 0:
        step2_messages.append("workflow.msg.rooms_missing")
    if len(project.work_items) == 0:
        step2_messages.append("workflow.msg.works_missing")
    if quality_report.blocks_count > 0:
        step2_messages.append("workflow.msg.quality_blockers")
    if len(project.rooms) > 0 and len(project.work_items) > 0 and quality_report.blocks_count == 0:
        step2_status = "done"
    elif len(project.rooms) > 0 or len(project.work_items) > 0:
        step2_status = "warning"
    else:
        step2_status = "blocked"

    step3_messages: list[str] = []
    if step2_status != "done":
        step3_messages.append("workflow.msg.rooms_works_incomplete")
    if not pricing:
        step3_messages.append("workflow.msg.pricing_not_selected")
    if selected_scenario and selected_scenario.invalid:
        step3_messages.append("workflow.msg.pricing_invalid")
    if completeness.score < int(get_or_create_pricing_policy(db).min_completeness_score_for_fixed or 70) and pricing_mode == "FIXED_TOTAL":
        step3_messages.append("workflow.msg.completeness_low_fixed")
    if pricing and not step3_messages:
        step3_status = "done"
    elif pricing and step2_status == "done":
        step3_status = "warning"
    else:
        step3_status = "blocked"

    profile = get_or_create_company_profile(db)
    step4_messages: list[str] = []
    if not profile.org_number:
        step4_messages.append("workflow.msg.company_org_missing")
    if not profile.vat_number:
        step4_messages.append("workflow.msg.company_vat_missing")
    if step3_status != "done":
        step4_messages.append("workflow.msg.pricing_required_for_offer")
    offer_status = _offer_status(project)
    if offer_status == "issued":
        step4_status = "done"
    elif step4_messages:
        step4_status = "blocked"
    elif offer_status == "draft":
        step4_status = "warning"
    else:
        step4_status = "warning"

    step5_messages: list[str] = []
    invoice_status = _invoice_status(project)
    draft_invoice = next((inv for inv in project.invoices if inv.status == "draft"), None)
    if step4_status == "blocked":
        step5_messages.append("workflow.msg.offer_required_for_invoice")
    if invoice_status == "issued":
        step5_status = "done"
    elif draft_invoice:
        step5_status = "warning"
    elif step5_messages:
        step5_status = "blocked"
    else:
        step5_status = "warning"

    steps = [
        WorkflowStep("project_data", "workflow.step.project_data", step1_status, step1_messages, f"/projects/{project.id}/edit"),
        WorkflowStep("rooms_works", "workflow.step.rooms_works", step2_status, step2_messages, f"/projects/{project.id}"),
        WorkflowStep("estimate_pricing", "workflow.step.estimate_pricing", step3_status, step3_messages, f"/projects/{project.id}/pricing"),
        WorkflowStep("offer", "workflow.step.offer", step4_status, step4_messages, f"/projects/{project.id}/offer"),
        WorkflowStep("invoice", "workflow.step.invoice", step5_status, step5_messages, f"/projects/{project.id}/invoices/"),
    ]

    recent_activity = (
        db.query(AuditEvent)
        .filter(
            ((AuditEvent.entity_type == "project") & (AuditEvent.entity_id == project.id))
            | ((AuditEvent.entity_type == "invoice") & (AuditEvent.entity_id.in_([inv.id for inv in project.invoices] or [-1])))
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(10)
        .all()
    )

    project_status = "draft"
    if invoice_status == "issued":
        project_status = "invoice_issued"
    elif invoice_status == "draft":
        project_status = "invoice_draft"
    elif offer_status == "issued":
        project_status = "offer_issued"
    elif step4_status != "blocked":
        project_status = "ready_for_offer"

    return {
        "project": project,
        "steps": [s.__dict__ for s in steps],
        "pricing_summary": pricing_summary,
        "bom_report": bom_report,
        "offer_status": offer_status,
        "invoice_status": invoice_status,
        "latest_invoice": draft_invoice or (project.invoices[-1] if project.invoices else None),
        "quality_report": quality_report,
        "completeness": completeness,
        "pricing_mode": pricing_summary.selected_mode,
        "pricing_scenarios": scenarios,
        "can_create_offer": step4_status != "blocked",
        "can_issue_offer": offer_status == "draft" and step4_status != "blocked",
        "can_create_invoice": step3_status == "done" and step4_status != "blocked",
        "can_issue_invoice": bool(draft_invoice),
        "blocking_reasons": [msg for s in steps if s.status == "blocked" for msg in s.messages],
        "materials_top": bom_report.line_items[:5],
        "activity": recent_activity,
        "workflow_status": project_status,
        "updated_at": date.today(),
    }
