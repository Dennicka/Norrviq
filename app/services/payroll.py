from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Invoice, Project, ProjectWorkerAssignment, Settings, Worker


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _as_decimal(value: Optional[Decimal]) -> Decimal:
    return Decimal(value or 0)


def _project_in_period(project: Project, from_date: date, to_date: date, db: Session) -> bool:
    start_date = project.actual_start_date or project.planned_start_date
    end_date = project.actual_end_date or project.planned_end_date

    if start_date or end_date:
        start = start_date or end_date
        end = end_date or start_date
        return start <= to_date and end >= from_date

    invoice_exists = (
        db.query(Invoice)
        .filter(
            Invoice.project_id == project.id,
            Invoice.issue_date >= from_date,
            Invoice.issue_date <= to_date,
        )
        .first()
        is not None
    )
    return invoice_exists


def get_assignments_for_period(
    db: Session, worker: Worker, from_date: date, to_date: date
) -> List[ProjectWorkerAssignment]:
    assignments = (
        db.query(ProjectWorkerAssignment)
        .join(Project)
        .filter(ProjectWorkerAssignment.worker_id == worker.id)
        .all()
    )

    return [a for a in assignments if _project_in_period(a.project, from_date, to_date, db)]


@dataclass
class WorkerPeriodSummary:
    worker: Worker
    total_planned_hours: Decimal
    total_actual_hours: Decimal

    gross_hourly_rate: Decimal
    gross_pay: Decimal
    employer_taxes: Decimal
    total_employer_cost: Decimal

    net_tax_percent: Decimal
    net_pay_approx: Decimal


def compute_worker_summary_for_period(
    db: Session,
    worker: Worker,
    settings: Settings,
    from_date: date,
    to_date: date,
) -> WorkerPeriodSummary:
    assignments = get_assignments_for_period(db, worker, from_date, to_date)

    total_planned_hours = _quantize(
        sum(_as_decimal(a.planned_hours) for a in assignments) or Decimal("0")
    )
    total_actual_hours = _quantize(
        sum(_as_decimal(a.actual_hours) for a in assignments) or Decimal("0")
    )

    gross_hourly_rate = _as_decimal(worker.hourly_rate) or _as_decimal(
        settings.default_worker_hourly_rate
    )
    gross_pay = _quantize(total_actual_hours * gross_hourly_rate)

    employer_tax_percent = _as_decimal(settings.employer_contributions_percent)
    employer_taxes = _quantize(gross_pay * employer_tax_percent / Decimal("100"))
    total_employer_cost = _quantize(gross_pay + employer_taxes)

    net_tax_percent = _as_decimal(
        worker.default_tax_percent_for_net or settings.default_worker_tax_percent_for_net
    )
    net_pay_approx = _quantize(gross_pay * (Decimal("1") - net_tax_percent / Decimal("100")))

    return WorkerPeriodSummary(
        worker=worker,
        total_planned_hours=total_planned_hours,
        total_actual_hours=total_actual_hours,
        gross_hourly_rate=_quantize(gross_hourly_rate),
        gross_pay=gross_pay,
        employer_taxes=employer_taxes,
        total_employer_cost=total_employer_cost,
        net_tax_percent=_quantize(net_tax_percent),
        net_pay_approx=net_pay_approx,
    )
