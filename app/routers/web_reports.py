from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
import csv
import io

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session, selectinload

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.invoice import Invoice
from app.models.project import Project
from app.models.settings import Settings, get_or_create_settings
from app.services.finance import compute_project_finance

router = APIRouter(prefix="/reports", tags=["reports"])


@dataclass
class PeriodReportSummary:
    from_date: date
    to_date: date
    total_work_sum_without_moms: Decimal
    total_moms_amount: Decimal
    total_rot_amount: Decimal
    total_client_pays: Decimal

    total_materials_cost: Decimal
    total_transport_cost: Decimal
    total_other_cost: Decimal
    total_salary_fund: Decimal
    total_employer_taxes: Decimal
    total_overhead_cost: Decimal
    total_expenses: Decimal
    total_profit: Decimal


def _resolve_period(from_date: date | None, to_date: date | None) -> tuple[date, date]:
    if from_date and to_date:
        return from_date, to_date

    today = date.today()
    first_day = today.replace(day=1)
    if first_day.month == 12:
        next_month = first_day.replace(year=first_day.year + 1, month=1, day=1)
    else:
        next_month = first_day.replace(month=first_day.month + 1, day=1)
    last_day = next_month - timedelta(days=1)

    return from_date or first_day, to_date or last_day


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _fetch_invoices(db: Session, from_date: date, to_date: date) -> list[Invoice]:
    return (
        db.query(Invoice)
        .options(selectinload(Invoice.project).selectinload(Project.client))
        .filter(Invoice.issue_date >= from_date, Invoice.issue_date <= to_date)
        .filter(Invoice.status != "cancelled")
        .all()
    )


def _calculate_summary(
    db: Session, invoices: list[Invoice], settings: Settings, from_date: date, to_date: date
) -> PeriodReportSummary:
    total_work_sum_without_moms = sum(
        (_decimal(inv.work_sum_without_moms) for inv in invoices), Decimal("0")
    )
    total_moms_amount = sum((_decimal(inv.moms_amount) for inv in invoices), Decimal("0"))
    total_rot_amount = sum((_decimal(inv.rot_amount) for inv in invoices), Decimal("0"))
    total_client_pays = sum(
        (_decimal(inv.client_pays_total) for inv in invoices), Decimal("0")
    )

    project_ids = {inv.project_id for inv in invoices}
    total_materials_cost = Decimal("0")
    total_transport_cost = Decimal("0")
    total_other_cost = Decimal("0")
    total_salary_fund = Decimal("0")
    total_employer_taxes = Decimal("0")
    total_overhead_cost = Decimal("0")
    total_expenses = Decimal("0")
    total_profit = Decimal("0")

    if project_ids:
        projects = db.query(Project).filter(Project.id.in_(project_ids)).all()
        for project in projects:
            summary = compute_project_finance(db, project, settings=settings)
            total_materials_cost += _decimal(summary.materials_cost)
            total_transport_cost += _decimal(summary.transport_cost)
            total_other_cost += _decimal(summary.other_cost)
            total_salary_fund += _decimal(summary.salary_fund)
            total_employer_taxes += _decimal(summary.employer_taxes)
            total_overhead_cost += _decimal(summary.overhead_cost)
            total_expenses += _decimal(summary.total_expenses)
            total_profit += _decimal(summary.profit)

    return PeriodReportSummary(
        from_date=from_date,
        to_date=to_date,
        total_work_sum_without_moms=total_work_sum_without_moms,
        total_moms_amount=total_moms_amount,
        total_rot_amount=total_rot_amount,
        total_client_pays=total_client_pays,
        total_materials_cost=total_materials_cost,
        total_transport_cost=total_transport_cost,
        total_other_cost=total_other_cost,
        total_salary_fund=total_salary_fund,
        total_employer_taxes=total_employer_taxes,
        total_overhead_cost=total_overhead_cost,
        total_expenses=total_expenses,
        total_profit=total_profit,
    )


@router.get("/period/", response_class=HTMLResponse)
def period_report(
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    from_date: date | None = None,
    to_date: date | None = None,
):
    from_date, to_date = _resolve_period(from_date, to_date)
    invoices = _fetch_invoices(db, from_date, to_date)
    settings_obj = get_or_create_settings(db)
    summary = _calculate_summary(
        db, invoices, settings=settings_obj, from_date=from_date, to_date=to_date
    )

    context = template_context(request, lang)
    context.update(
        {
            "summary": summary,
            "invoices": invoices,
            "from_date": from_date,
            "to_date": to_date,
        }
    )
    return templates.TemplateResponse("reports/period.html", context)


@router.get("/period/export.csv")
def period_report_csv(
    request: Request,
    db: Session = Depends(get_db),
    _lang: str = Depends(get_current_lang),
    from_date: date | None = None,
    to_date: date | None = None,
):
    from_date, to_date = _resolve_period(from_date, to_date)
    invoices = _fetch_invoices(db, from_date, to_date)
    settings_obj = get_or_create_settings(db)
    _calculate_summary(
        db, invoices, settings=settings_obj, from_date=from_date, to_date=to_date
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "invoice_number",
            "issue_date",
            "project_name",
            "client_name",
            "work_sum_without_moms",
            "moms_amount",
            "rot_amount",
            "client_pays_total",
            "status",
        ]
    )
    for invoice in invoices:
        project = invoice.project
        writer.writerow(
            [
                invoice.invoice_number,
                invoice.issue_date,
                project.name if project else "",
                project.client.name if project and project.client else "",
                invoice.work_sum_without_moms,
                invoice.moms_amount,
                invoice.rot_amount,
                invoice.client_pays_total,
                invoice.status,
            ]
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=\"norrviq_period_report.csv\""
        },
    )
