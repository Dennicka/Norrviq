from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session, selectinload

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.project import Project
from app.models.settings import get_or_create_settings
from app.services.finance import compute_project_finance

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@router.get("/", response_class=HTMLResponse)
def analytics_overview(
    request: Request,
    status: str | None = Query(None),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    query = db.query(Project).options(selectinload(Project.client))

    if status:
        query = query.filter(Project.status == status)

    parsed_from = _parse_date(from_date)
    parsed_to = _parse_date(to_date)

    # Для фильтра даты используем planned_start_date, чтобы видеть плановые сроки проектов.
    if parsed_from:
        query = query.filter(Project.planned_start_date >= parsed_from)
    if parsed_to:
        query = query.filter(Project.planned_start_date <= parsed_to)

    projects = query.all()
    settings = get_or_create_settings(db)
    data = []
    for project in projects:
        summary = compute_project_finance(db, project, settings=settings)
        start_date = project.actual_start_date or project.planned_start_date
        end_date = project.actual_end_date or project.planned_end_date
        data.append(
            {
                "project": project,
                "client_name": project.client.name if project.client else "",
                "status": project.status,
                "start_date": start_date,
                "end_date": end_date,
                "revenue": summary.client_pays_total,
                "total_expenses": summary.total_expenses,
                "profit": summary.profit,
                "margin_percent": summary.margin_percent,
            }
        )

    statuses = ["draft", "sent", "accepted", "in_progress", "done"]

    context = template_context(request, lang)
    context.update(
        {
            "projects_data": data,
            "status_filter": status or "",
            "from_date": parsed_from.isoformat() if parsed_from else "",
            "to_date": parsed_to.isoformat() if parsed_to else "",
            "statuses": statuses,
        }
    )
    return templates.TemplateResponse("analytics/overview.html", context)
