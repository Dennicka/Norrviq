from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session, selectinload

from app.models.project import ProjectWorkItem
from app.models.work_package import WorkPackageTemplate
from app.models.worktype import WorkType
from app.services.work_packages import list_active_packages


@dataclass(frozen=True)
class PackageApplySummary:
    created_count: int
    updated_count: int


@dataclass(frozen=True)
class PackageRemoveSummary:
    deleted_count: int


def apply_package(
    db: Session,
    project_id: int,
    package_code: str,
    scope_mode: str,
    selected_room_ids: list[int] | None,
) -> PackageApplySummary:
    template = _get_template(db, package_code)
    if template is None:
        return PackageApplySummary(created_count=0, updated_count=0)

    normalized_scope = "SELECTED_ROOMS" if (scope_mode or "").upper() == "SELECTED_ROOMS" else "WHOLE_PROJECT"
    rooms_json = _rooms_json(selected_room_ids) if normalized_scope == "SELECTED_ROOMS" else None

    work_types = {row.code: row for row in db.query(WorkType).filter(WorkType.is_active.is_(True)).all()}
    created_count = 0
    updated_count = 0

    for line in template.items:
        work_type = work_types.get(line.work_type_code)
        if work_type is None:
            continue

        existing = (
            db.query(ProjectWorkItem)
            .filter(
                ProjectWorkItem.project_id == project_id,
                ProjectWorkItem.work_type_id == work_type.id,
                ProjectWorkItem.source_package_code == package_code,
            )
            .first()
        )

        basis_type = (line.basis_type or "wall_area_m2").lower()
        if existing:
            if _sync_work_item(existing, package_code, normalized_scope, rooms_json, basis_type, line, work_type):
                updated_count += 1
            continue

        db.add(
            ProjectWorkItem(
                project_id=project_id,
                work_type_id=work_type.id,
                room_id=None,
                quantity=Decimal("1"),
                difficulty_factor=line.difficulty_factor or Decimal("1"),
                scope_mode=normalized_scope,
                basis_type=basis_type,
                selected_room_ids_json=rooms_json,
                pricing_mode=(line.pricing_mode or "HOURLY").upper(),
                norm_hours_per_unit=line.norm_hours_per_unit or work_type.hours_per_unit,
                unit_rate_ex_vat=line.unit_rate_ex_vat,
                hourly_rate_ex_vat=line.hourly_rate_ex_vat,
                fixed_total_ex_vat=line.fixed_total_ex_vat,
                source_group_ref=f"pkg:{package_code}",
                source_package_code=package_code,
                source_package_version=1,
                comment=_comment_from_layers(line.coats, line.layers),
            )
        )
        created_count += 1

    db.commit()
    return PackageApplySummary(created_count=created_count, updated_count=updated_count)


def remove_package(db: Session, project_id: int, package_code: str) -> PackageRemoveSummary:
    rows = (
        db.query(ProjectWorkItem)
        .filter(
            ProjectWorkItem.project_id == project_id,
            ProjectWorkItem.source_package_code == package_code,
        )
        .all()
    )
    deleted_count = len(rows)
    for row in rows:
        db.delete(row)
    db.commit()
    return PackageRemoveSummary(deleted_count=deleted_count)


def list_applied_package_codes(db: Session, project_id: int) -> list[str]:
    codes = (
        db.query(ProjectWorkItem.source_package_code)
        .filter(
            ProjectWorkItem.project_id == project_id,
            ProjectWorkItem.source_package_code.is_not(None),
        )
        .distinct()
        .all()
    )
    return sorted([code for (code,) in codes if code])


def _get_template(db: Session, package_code: str) -> WorkPackageTemplate | None:
    list_active_packages(db)
    return (
        db.query(WorkPackageTemplate)
        .options(selectinload(WorkPackageTemplate.items))
        .filter(WorkPackageTemplate.code == package_code, WorkPackageTemplate.is_active.is_(True))
        .first()
    )


def _sync_work_item(existing: ProjectWorkItem, package_code: str, scope_mode: str, rooms_json: str | None, basis_type: str, line, work_type: WorkType) -> bool:
    changed = False
    updates: dict[str, object] = {
        "scope_mode": scope_mode,
        "selected_room_ids_json": rooms_json,
        "basis_type": basis_type,
        "pricing_mode": (line.pricing_mode or "HOURLY").upper(),
        "norm_hours_per_unit": line.norm_hours_per_unit or work_type.hours_per_unit,
        "unit_rate_ex_vat": line.unit_rate_ex_vat,
        "hourly_rate_ex_vat": line.hourly_rate_ex_vat,
        "fixed_total_ex_vat": line.fixed_total_ex_vat,
        "difficulty_factor": line.difficulty_factor or Decimal("1"),
        "source_package_code": package_code,
        "source_package_version": 1,
        "source_group_ref": f"pkg:{package_code}",
        "comment": _comment_from_layers(line.coats, line.layers),
    }

    for field, value in updates.items():
        if getattr(existing, field) != value:
            setattr(existing, field, value)
            changed = True
    return changed


def _rooms_json(selected_room_ids: list[int] | None) -> str:
    values = sorted({int(room_id) for room_id in (selected_room_ids or []) if str(room_id).isdigit()})
    return json.dumps(values)


def _comment_from_layers(coats: Decimal | None, layers: Decimal | None) -> str | None:
    bits = []
    if coats is not None:
        bits.append(f"coats={coats}")
    if layers is not None:
        bits.append(f"layers={layers}")
    return "; ".join(bits) if bits else None
