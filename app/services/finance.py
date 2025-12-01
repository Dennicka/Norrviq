from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models.project import Project, ProjectWorkItem, ProjectWorkerAssignment
from app.models.settings import Settings, get_or_create_settings
from app.models.worker import Worker


@dataclass
class ProjectFinanceSummary:
    work_sum_without_moms: Decimal
    moms_amount: Decimal
    rot_amount: Decimal
    client_pays_total: Decimal

    materials_cost: Decimal
    transport_cost: Decimal
    other_cost: Decimal

    salary_fund: Decimal
    employer_taxes: Decimal
    total_salary_cost: Decimal

    overhead_cost: Decimal
    total_expenses: Decimal

    profit: Decimal
    margin_percent: Optional[Decimal]


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def calculate_salary_costs(db: Session, project: Project, settings: Settings | None = None) -> Dict[str, Decimal]:
    """Возвращает зарплатные расходы для проекта."""

    settings = settings or get_or_create_settings(db)
    default_rate = Decimal(str(settings.default_worker_hourly_rate or 0))
    employer_rate = Decimal(str(settings.employer_contributions_percent or 0))

    salary_fund = Decimal("0")

    assignments: list[ProjectWorkerAssignment] = getattr(project, "worker_assignments", [])
    for assignment in assignments:
        hours = Decimal(str(assignment.actual_hours or 0))
        worker: Worker | None = assignment.worker or db.get(Worker, assignment.worker_id)
        hourly_rate = worker.hourly_rate if worker and worker.hourly_rate is not None else default_rate
        hourly_rate = Decimal(str(hourly_rate or 0))

        salary_fund += hours * hourly_rate

    salary_fund = _quantize(salary_fund)
    employer_taxes = _quantize(salary_fund * employer_rate / Decimal("100"))
    total_salary_cost = _quantize(salary_fund + employer_taxes)

    return {
        "salary_fund": salary_fund,
        "employer_taxes": employer_taxes,
        "total_salary_cost": total_salary_cost,
    }


def calculate_cost_items(db: Session, project: Project) -> Dict[str, Decimal]:
    """Суммирует расходы проекта по категориям."""

    totals = {
        "materials_cost": Decimal("0"),
        "transport_cost": Decimal("0"),
        "other_cost": Decimal("0"),
    }

    for item in getattr(project, "cost_items", []):
        code = item.category.code if item.category else None
        amount = Decimal(str(item.amount or 0))

        if code == "MATERIALS":
            totals["materials_cost"] += amount
        elif code in {"TRANSPORT", "FUEL", "PARKING"}:
            totals["transport_cost"] += amount
        else:
            totals["other_cost"] += amount

    totals = {key: _quantize(value) for key, value in totals.items()}
    totals["total_extra_cost"] = _quantize(sum(totals.values(), Decimal("0")))
    return totals


def _sum_work_without_moms(project: Project) -> Decimal:
    items: list[ProjectWorkItem] = getattr(project, "work_items", [])
    return _quantize(
        sum(
            (Decimal(str(item.calculated_cost_without_moms or 0)) for item in items),
            Decimal("0"),
        )
    )


def compute_project_finance(
    db: Session, project: Project, settings: Settings | None = None
) -> ProjectFinanceSummary:
    settings = settings or get_or_create_settings(db)

    work_sum_without_moms = _sum_work_without_moms(project)
    moms_amount = _quantize(
        work_sum_without_moms * Decimal(str(settings.moms_percent or 0)) / Decimal("100")
    )

    uses_rot = getattr(project, "uses_rot", None)
    rot_enabled = project.use_rot if uses_rot is None else uses_rot
    rot_amount = _quantize(
        work_sum_without_moms * Decimal(str(settings.rot_percent or 0)) / Decimal("100")
    )
    if not rot_enabled:
        rot_amount = Decimal("0.00")

    client_pays_total = _quantize(work_sum_without_moms + moms_amount - rot_amount)

    costs = calculate_cost_items(db, project)
    salary_costs = calculate_salary_costs(db, project, settings=settings)

    base_for_overhead = _quantize(
        costs["materials_cost"]
        + costs["transport_cost"]
        + costs["other_cost"]
        + salary_costs["total_salary_cost"]
    )
    overhead_cost = _quantize(
        base_for_overhead * Decimal(str(settings.default_overhead_percent or 0)) / Decimal("100")
    )

    total_expenses = _quantize(
        costs["materials_cost"]
        + costs["transport_cost"]
        + costs["other_cost"]
        + salary_costs["total_salary_cost"]
        + overhead_cost
    )
    profit = _quantize(client_pays_total - total_expenses)
    margin_percent: Optional[Decimal]
    if client_pays_total > 0:
        margin_percent = _quantize(profit / client_pays_total * Decimal("100"))
    else:
        margin_percent = None

    return ProjectFinanceSummary(
        work_sum_without_moms=work_sum_without_moms,
        moms_amount=moms_amount,
        rot_amount=rot_amount,
        client_pays_total=client_pays_total,
        materials_cost=costs["materials_cost"],
        transport_cost=costs["transport_cost"],
        other_cost=costs["other_cost"],
        salary_fund=salary_costs["salary_fund"],
        employer_taxes=salary_costs["employer_taxes"],
        total_salary_cost=salary_costs["total_salary_cost"],
        overhead_cost=overhead_cost,
        total_expenses=total_expenses,
        profit=profit,
        margin_percent=margin_percent,
    )


def calculate_project_financials(db: Session, project: Project) -> None:
    """
    Рассчитывает финансовые показатели проекта и обновляет соответствующие поля.
    """

    summary = compute_project_finance(db, project)

    project.work_sum_without_moms = summary.work_sum_without_moms
    project.moms_amount = summary.moms_amount
    project.rot_amount = summary.rot_amount
    project.client_pays_total = summary.client_pays_total

    project.salary_fund = summary.salary_fund
    project.employer_taxes = summary.employer_taxes
    project.total_salary_cost = summary.total_salary_cost

    project.materials_cost = summary.materials_cost
    # В существующей схеме нет отдельного поля для транспорта, поэтому сохраняем в fuel_cost.
    project.fuel_cost = summary.transport_cost
    project.other_cost = summary.other_cost

    project.overhead_amount = summary.overhead_cost
    project.total_cost = summary.total_expenses
    project.profit = summary.profit
    project.margin_percent = summary.margin_percent

    db.commit()
