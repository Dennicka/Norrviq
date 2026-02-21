import csv
from calendar import monthrange
from datetime import date
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.settings import Settings, get_or_create_settings
from app.models.worker import Worker
from app.services.payroll import compute_worker_summary_for_period, get_assignments_for_period


router = APIRouter(prefix="/payroll", tags=["payroll"])


def _default_period(today: date) -> tuple[date, date]:
    start = today.replace(day=1)
    last_day = monthrange(today.year, today.month)[1]
    end = today.replace(day=last_day)
    return start, end


def _resolve_period(from_date: date | None, to_date: date | None) -> tuple[date, date]:
    if from_date and to_date:
        return from_date, to_date

    today = date.today()
    return _default_period(today)


@router.get("/summary/", response_class=HTMLResponse)
def payroll_summary(
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    from_date: date | None = None,
    to_date: date | None = None,
    include_inactive: bool = False,
):
    period_from, period_to = _resolve_period(from_date, to_date)
    settings_obj: Settings = get_or_create_settings(db)

    workers_query = db.query(Worker)
    if not include_inactive:
        workers_query = workers_query.filter(Worker.is_active.is_(True))
    workers = workers_query.all()

    summaries = [
        compute_worker_summary_for_period(db, worker, settings_obj, period_from, period_to)
        for worker in workers
    ]

    context = template_context(request, lang)
    context.update(
        {
            "summaries": summaries,
            "from_date": period_from,
            "to_date": period_to,
            "include_inactive": include_inactive,
        }
    )
    return templates.TemplateResponse(request, "payroll/summary.html", context)


@router.get("/worker/{worker_id}/", response_class=HTMLResponse)
def payroll_worker_detail(
    worker_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    from_date: date | None = None,
    to_date: date | None = None,
):
    worker = db.get(Worker, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    period_from, period_to = _resolve_period(from_date, to_date)

    assignments = get_assignments_for_period(db, worker, period_from, period_to)
    settings_obj: Settings = get_or_create_settings(db)
    summary = compute_worker_summary_for_period(db, worker, settings_obj, period_from, period_to)

    context = template_context(request, lang)
    context.update(
        {
            "worker": worker,
            "assignments": assignments,
            "summary": summary,
            "from_date": period_from,
            "to_date": period_to,
        }
    )
    return templates.TemplateResponse(request, "payroll/worker_detail.html", context)


@router.get("/summary/export.csv")
def payroll_summary_csv(
    db: Session = Depends(get_db),
    from_date: date | None = None,
    to_date: date | None = None,
    include_inactive: bool = False,
):
    period_from, period_to = _resolve_period(from_date, to_date)
    settings_obj: Settings = get_or_create_settings(db)

    workers_query = db.query(Worker)
    if not include_inactive:
        workers_query = workers_query.filter(Worker.is_active.is_(True))
    workers = workers_query.all()

    summaries = [
        compute_worker_summary_for_period(db, worker, settings_obj, period_from, period_to)
        for worker in workers
    ]

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "worker_name",
            "worker_role",
            "total_planned_hours",
            "total_actual_hours",
            "hourly_rate",
            "gross_pay",
            "employer_taxes",
            "total_employer_cost",
            "net_tax_percent",
            "net_pay_approx",
        ]
    )

    for summary in summaries:
        writer.writerow(
            [
                summary.worker.name,
                summary.worker.role or "",
                summary.total_planned_hours,
                summary.total_actual_hours,
                summary.gross_hourly_rate,
                summary.gross_pay,
                summary.employer_taxes,
                summary.total_employer_cost,
                summary.net_tax_percent,
                summary.net_pay_approx,
            ]
        )

    headers = {"Content-Disposition": 'attachment; filename="norrviq_payroll_summary.csv"'}
    return Response(content=output.getvalue(), media_type="text/csv", headers=headers)
