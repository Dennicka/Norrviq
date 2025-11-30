from decimal import Decimal
from typing import Dict, Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.project import ProjectWorkerAssignment
from app.models.settings import Settings
from app.models.worker import Worker


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def get_worker_aggregates(
    db: Session, workers: Iterable[Worker], settings: Settings
) -> Dict[int, Dict[str, Decimal]]:
    worker_list = list(workers)
    worker_ids = [w.id for w in worker_list if w.id is not None]
    aggregates: Dict[int, Dict[str, Decimal]] = {
        w.id: {"total_hours": Decimal("0"), "total_gross": Decimal("0"), "approx_net": Decimal("0")}
        for w in worker_list
        if w.id is not None
    }

    if worker_ids:
        rows = (
            db.query(
                ProjectWorkerAssignment.worker_id,
                func.coalesce(func.sum(ProjectWorkerAssignment.actual_hours), 0),
            )
            .filter(ProjectWorkerAssignment.worker_id.in_(worker_ids))
            .group_by(ProjectWorkerAssignment.worker_id)
            .all()
        )
        for worker_id, total_hours in rows:
            aggregates[worker_id]["total_hours"] = _quantize(Decimal(total_hours or 0))

    for worker in worker_list:
        if worker.id is None:
            continue
        total_hours = aggregates[worker.id]["total_hours"]
        hourly_rate = worker.hourly_rate or settings.default_worker_hourly_rate or Decimal("0")
        total_gross = total_hours * Decimal(hourly_rate)
        tax_percent = Decimal(settings.default_worker_tax_percent_for_net or 0)
        approx_net = total_gross * (Decimal(1) - tax_percent / Decimal(100))

        aggregates[worker.id]["total_gross"] = _quantize(total_gross)
        aggregates[worker.id]["approx_net"] = _quantize(approx_net)

    return aggregates
