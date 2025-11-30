from collections import defaultdict
from decimal import Decimal
from typing import Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.project import Project, ProjectWorkItem
from app.models.worktype import WorkType


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def get_profit_by_month(db: Session) -> List[Dict]:
    year_expr = func.strftime("%Y", Project.created_at).label("year")
    month_expr = func.strftime("%m", Project.created_at).label("month")

    rows = (
        db.query(
            year_expr,
            month_expr,
            func.coalesce(func.sum(Project.client_pays_total), 0).label("revenue"),
            func.coalesce(func.sum(Project.total_cost), 0).label("total_cost"),
            func.coalesce(func.sum(Project.profit), 0).label("profit"),
        )
        .group_by(year_expr, month_expr)
        .order_by(year_expr, month_expr)
        .all()
    )

    result = []
    for row in rows:
        result.append(
            {
                "year": int(row.year),
                "month": int(row.month),
                "revenue": _quantize(Decimal(row.revenue or 0)),
                "total_cost": _quantize(Decimal(row.total_cost or 0)),
                "profit": _quantize(Decimal(row.profit or 0)),
            }
        )
    return result


def get_profit_by_client(db: Session) -> List[Dict]:
    rows = (
        db.query(
            Client.id.label("client_id"),
            Client.name.label("client_name"),
            func.coalesce(func.sum(Project.client_pays_total), 0).label("revenue"),
            func.coalesce(func.sum(Project.profit), 0).label("profit"),
        )
        .join(Project, Project.client_id == Client.id)
        .group_by(Client.id)
        .order_by(Client.id)
        .all()
    )

    return [
        {
            "client_id": row.client_id,
            "client_name": row.client_name,
            "revenue": _quantize(Decimal(row.revenue or 0)),
            "profit": _quantize(Decimal(row.profit or 0)),
        }
        for row in rows
    ]


def get_profit_by_worktype_category(db: Session) -> List[Dict]:
    revenue_rows = (
        db.query(
            ProjectWorkItem.project_id,
            WorkType.category,
            func.coalesce(func.sum(ProjectWorkItem.calculated_cost_without_moms), 0).label(
                "revenue"
            ),
        )
        .join(WorkType, ProjectWorkItem.work_type_id == WorkType.id)
        .group_by(ProjectWorkItem.project_id, WorkType.category)
        .all()
    )

    project_profits = {
        row.id: Decimal(row.profit or 0)
        for row in db.query(Project.id, Project.profit).all()
    }

    project_revenues: Dict[int, Dict[str, Decimal]] = defaultdict(dict)
    for row in revenue_rows:
        category = row.category or "unknown"
        project_revenues[row.project_id][category] = Decimal(row.revenue or 0)

    category_totals: Dict[str, Dict[str, Decimal]] = defaultdict(
        lambda: {"revenue": Decimal("0"), "profit": Decimal("0")}
    )

    for project_id, categories in project_revenues.items():
        total_revenue = sum(categories.values())
        profit = project_profits.get(project_id, Decimal("0"))
        for category, revenue in categories.items():
            share_profit = Decimal("0")
            if total_revenue:
                share_profit = profit * (revenue / total_revenue)
            category_totals[category]["revenue"] += revenue
            category_totals[category]["profit"] += share_profit

    return [
        {
            "category": category,
            "revenue": _quantize(values["revenue"]),
            "profit": _quantize(values["profit"]),
        }
        for category, values in category_totals.items()
    ]
