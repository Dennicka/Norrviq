from decimal import Decimal
from typing import Dict

from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.worker import Worker
from app.models.settings import get_or_create_settings


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def calculate_salary_costs(db: Session, project: Project) -> Dict[str, Decimal]:
    """
    Возвращает словарь с ключами salary_fund, employer_taxes, total_salary_cost.
    Использует фактические часы назначений и ставки работников либо дефолтные из настроек.
    """

    settings = get_or_create_settings(db)
    default_rate = Decimal(str(settings.default_worker_hourly_rate or 0))
    employer_rate = Decimal(str(settings.employer_contributions_percent or 0))

    salary_fund = Decimal("0")

    for assignment in project.worker_assignments:
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
    """
    Суммирует расходы проекта по категориям и возвращает словарь с итогами.
    """

    totals = {
        "materials_cost": Decimal("0"),
        "fuel_cost": Decimal("0"),
        "parking_cost": Decimal("0"),
        "rent_cost": Decimal("0"),
        "other_cost": Decimal("0"),
    }

    for item in project.cost_items:
        code = item.category.code if item.category else None
        amount = Decimal(str(item.amount or 0))

        if code == "MATERIALS":
            totals["materials_cost"] += amount
        elif code == "FUEL":
            totals["fuel_cost"] += amount
        elif code == "PARKING":
            totals["parking_cost"] += amount
        elif code == "RENT":
            totals["rent_cost"] += amount
        else:
            totals["other_cost"] += amount

    totals = {key: _quantize(value) for key, value in totals.items()}
    total_extra_cost = _quantize(sum(totals.values(), Decimal("0")))

    totals["total_extra_cost"] = total_extra_cost
    return totals


def calculate_project_financials(db: Session, project: Project) -> None:
    """
    Рассчитывает финансовые показатели проекта и обновляет соответствующие поля.
    """

    settings = get_or_create_settings(db)

    salary_costs = calculate_salary_costs(db, project)
    cost_items = calculate_cost_items(db, project)

    revenue = Decimal(str(project.client_pays_total or 0))

    materials_cost = cost_items.get("materials_cost", Decimal("0"))
    fuel_cost = cost_items.get("fuel_cost", Decimal("0"))
    parking_cost = cost_items.get("parking_cost", Decimal("0"))
    rent_cost = cost_items.get("rent_cost", Decimal("0"))
    other_cost = cost_items.get("other_cost", Decimal("0"))

    direct_costs = salary_costs["total_salary_cost"] + materials_cost + fuel_cost + parking_cost + rent_cost + other_cost

    overhead_rate = Decimal(str(settings.default_overhead_percent or 0)) / Decimal("100")
    overhead_amount = _quantize(direct_costs * overhead_rate)

    total_cost = _quantize(direct_costs + overhead_amount)
    profit = _quantize(revenue - total_cost)

    margin_percent = Decimal("0.00")
    if revenue != 0:
        margin_percent = (profit / revenue * Decimal("100")).quantize(Decimal("0.01"))

    project.salary_fund = salary_costs["salary_fund"]
    project.employer_taxes = salary_costs["employer_taxes"]
    project.total_salary_cost = salary_costs["total_salary_cost"]

    project.materials_cost = materials_cost
    project.fuel_cost = fuel_cost
    project.parking_cost = parking_cost
    project.rent_cost = rent_cost
    project.other_cost = other_cost

    project.overhead_amount = overhead_amount
    project.total_cost = total_cost
    project.profit = profit
    project.margin_percent = margin_percent

    db.commit()
