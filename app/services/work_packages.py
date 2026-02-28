from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.project import ProjectWorkItem
from app.models.work_package import WorkPackageTemplate
from app.models.worktype import WorkType


PACKAGE_CODES = {
    "masking_floors_project",
    "paint_ceiling_2coats_project",
    "paint_walls_2coats_project",
    "skim_coat_2layers_sanding_project",
    "trims_frames_perimeter_project",
    "openings_count_project",
}


def package_label(template: WorkPackageTemplate, lang: str) -> str:
    if lang == "ru":
        return template.name_ru
    if lang == "en":
        return template.name_en
    return template.name_sv


def list_active_packages(db: Session) -> list[WorkPackageTemplate]:
    return (
        db.query(WorkPackageTemplate)
        .filter(WorkPackageTemplate.is_active.is_(True))
        .order_by(WorkPackageTemplate.id.asc())
        .all()
    )


def apply_package_to_project(db: Session, *, project_id: int, package_code: str) -> int:
    template = (
        db.query(WorkPackageTemplate)
        .filter(WorkPackageTemplate.code == package_code, WorkPackageTemplate.is_active.is_(True))
        .first()
    )
    if not template:
        return 0

    all_work_types = db.query(WorkType).filter(WorkType.is_active.is_(True)).all()
    work_types = {wt.code: wt for wt in all_work_types}
    created_count = 0
    for row in template.items:
        wt = work_types.get(row.work_type_code) or _fallback_work_type(all_work_types, row.work_type_code)
        if not wt:
            continue
        item = ProjectWorkItem(
            project_id=project_id,
            work_type_id=wt.id,
            room_id=None,
            quantity=Decimal("1"),
            difficulty_factor=row.difficulty_factor or Decimal("1"),
            scope_mode=(row.scope_mode or "PROJECT").upper(),
            basis_type=(row.basis_type or "wall_area_m2").lower(),
            pricing_mode=(row.pricing_mode or "HOURLY").upper(),
            norm_hours_per_unit=row.norm_hours_per_unit or wt.hours_per_unit,
            unit_rate_ex_vat=row.unit_rate_ex_vat,
            hourly_rate_ex_vat=row.hourly_rate_ex_vat,
            fixed_total_ex_vat=row.fixed_total_ex_vat,
            source_group_ref=f"pkg:{template.code}",
            comment=_comment_from_layers(row.coats, row.layers),
        )
        db.add(item)
        created_count += 1
    return created_count


def _comment_from_layers(coats: Decimal | None, layers: Decimal | None) -> str | None:
    bits = []
    if coats is not None:
        bits.append(f"coats={coats}")
    if layers is not None:
        bits.append(f"layers={layers}")
    return "; ".join(bits) if bits else None


def _fallback_work_type(work_types: list[WorkType], code: str) -> WorkType | None:
    aliases = {
        "MASK_FLOOR": ["mask", "protect", "floor", "укрыв", "golv"],
        "PAINT_CEILING": ["ceiling", "tak", "потол"],
        "PAINT_WALL": ["wall", "vägg", "стен"],
        "SKIM_WALL": ["skim", "putty", "spack", "шпат"],
        "SAND_WALL": ["sand", "slip", "шлиф"],
        "PAINT_TRIM": ["trim", "plint", "sockel", "плинт"],
        "OPENINGS": ["opening", "openings", "проем", "öppn"],
    }
    markers = aliases.get(code, [])
    for wt in work_types:
        hay = " ".join([str(wt.code or ""), str(wt.category or ""), str(wt.name_ru or ""), str(wt.name_sv or "")]).lower()
        if markers and any(m in hay for m in markers):
            return wt
    return None
