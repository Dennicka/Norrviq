from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.services.material_norms import aggregate_totals, build_project_material_bom


@dataclass
class MaterialNeedRow:
    material_name: str
    source_work_item_id: int
    rule_id: int
    basis_type: str
    basis_quantity: Decimal
    norm_value: Decimal
    waste_factor_pct: Decimal
    calculated_quantity: Decimal
    material_unit: str


@dataclass
class MaterialNeedTotal:
    material_name: str
    material_unit: str
    total_quantity: Decimal


def calculate_material_needs_for_project(db: Session, project_id: int) -> tuple[list[MaterialNeedRow], list[MaterialNeedTotal]]:
    report = build_project_material_bom(project_id, db)
    rows: list[MaterialNeedRow] = []
    for idx, line in enumerate(report.line_items, start=1):
        rows.append(
            MaterialNeedRow(
                material_name=line.material_name,
                source_work_item_id=idx,
                rule_id=line.material_id or 0,
                basis_type=line.basis_type,
                basis_quantity=line.basis_value,
                norm_value=Decimal("0"),
                waste_factor_pct=Decimal("0"),
                calculated_quantity=line.theoretical_qty,
                material_unit=line.unit,
            )
        )
    totals = [MaterialNeedTotal(material_name=row.material_name, material_unit=row.material_unit, total_quantity=row.total_quantity) for row in aggregate_totals(report)]
    return rows, totals
