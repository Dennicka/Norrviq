from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.material_catalog_item import MaterialCatalogItem
from app.models.material_norm import MaterialConsumptionNorm
from app.models.worktype import WorkType


def _upsert_work_type(db: Session, *, code: str, name_ru: str, name_sv: str, name_en: str, unit: str = "m2", category: str = "paint", hours_per_unit: Decimal = Decimal("0.25")) -> WorkType:
    row = db.query(WorkType).filter(WorkType.code == code).first()
    if row is None:
        row = WorkType(
            code=code,
            category=category,
            unit=unit,
            name_ru=name_ru,
            name_sv=name_sv,
            description_ru=name_en,
            description_sv=name_sv,
            hours_per_unit=hours_per_unit,
            is_active=True,
        )
        db.add(row)
        db.flush()
        return row
    row.is_active = True
    if not row.category:
        row.category = category
    if not row.unit:
        row.unit = unit
    return row


def _upsert_material(db: Session, *, code: str, name: str, unit: str, package_size: Decimal, price_ex_vat: Decimal) -> MaterialCatalogItem:
    row = db.query(MaterialCatalogItem).filter(MaterialCatalogItem.material_code == code).first()
    if row is None:
        row = MaterialCatalogItem(
            material_code=code,
            name=name,
            unit=unit,
            package_size=package_size,
            package_unit=unit,
            price_ex_vat=price_ex_vat,
            vat_rate_pct=Decimal("25"),
            supplier_name="Default",
            is_active=True,
            is_default_for_material=True,
        )
        db.add(row)
        db.flush()
        return row
    row.is_active = True
    row.is_default_for_material = True
    return row


def _upsert_norm(db: Session, *, work_type_code: str, material: MaterialCatalogItem, qty_per_basis: Decimal, basis_type: str = "m2", material_unit: str = "l") -> None:
    row = (
        db.query(MaterialConsumptionNorm)
        .filter(MaterialConsumptionNorm.work_type_code == work_type_code, MaterialConsumptionNorm.material_catalog_item_id == material.id)
        .first()
    )
    if row is None:
        row = MaterialConsumptionNorm(
            name=f"{work_type_code}:{material.material_code}",
            active=True,
            is_active=True,
            material_name=material.name,
            material_category="paint",
            applies_to_work_type=work_type_code,
            work_type_code=work_type_code,
            basis_type=basis_type,
            consumption_qty=qty_per_basis,
            per_basis_qty=Decimal("1"),
            per_basis_unit=basis_type,
            material_unit=material_unit,
            layers_multiplier_enabled=True,
            coats_multiplier_mode="USE_WORK_ITEM_QUANTITY",
            waste_percent=Decimal("10"),
            consumption_value=qty_per_basis,
            consumption_unit="per_1_m2",
            package_size=material.package_size,
            package_unit=material.package_unit,
            material_catalog_item_id=material.id,
            default_unit_price_sek=material.price_ex_vat,
        )
        db.add(row)
        return
    row.active = True
    row.is_active = True
    row.layers_multiplier_enabled = True
    row.coats_multiplier_mode = "USE_WORK_ITEM_QUANTITY"


def seed_defaults(db: Session) -> None:
    work_types = [
        ("MASK_FLOOR", "Защита пола", "Golvmaskering", "Floor masking", "m2", Decimal("0.08")),
        ("PAINT_CEILING", "Покраска потолка", "Måla tak", "Paint ceiling", "m2", Decimal("0.15")),
        ("PAINT_TRIM", "Покраска плинтусов", "Måla lister", "Paint trim", "m", Decimal("0.12")),
        ("PAINT_WALL", "Покраска стен", "Måla vägg", "Paint wall", "m2", Decimal("0.18")),
        ("PRIMER_WALL", "Грунт стен", "Grunda vägg", "Prime wall", "m2", Decimal("0.12")),
        ("SAND_WALL", "Шлифовка стен", "Slipa vägg", "Sand wall", "m2", Decimal("0.10")),
        ("SKIM_WALL", "Шпаклевка стен", "Spackla vägg", "Skim wall", "m2", Decimal("0.20")),
        ("SPOT_REPAIR", "Локальный ремонт", "Laga lokalt", "Spot repair", "m2", Decimal("0.10")),
    ]
    for code, ru, sv, en, unit, hpu in work_types:
        _upsert_work_type(db, code=code, name_ru=ru, name_sv=sv, name_en=en, unit=unit, hours_per_unit=hpu)

    wall_paint = _upsert_material(db, code="wall_paint", name="Wall paint", unit="l", package_size=Decimal("10"), price_ex_vat=Decimal("699"))
    ceiling_paint = _upsert_material(db, code="ceiling_paint", name="Ceiling paint", unit="l", package_size=Decimal("10"), price_ex_vat=Decimal("649"))
    primer = _upsert_material(db, code="primer", name="Primer", unit="l", package_size=Decimal("5"), price_ex_vat=Decimal("399"))
    spackle = _upsert_material(db, code="spackle", name="Spackle", unit="kg", package_size=Decimal("10"), price_ex_vat=Decimal("249"))
    sanding = _upsert_material(db, code="sanding_paper", name="Sanding paper", unit="pcs", package_size=Decimal("25"), price_ex_vat=Decimal("129"))
    masking = _upsert_material(db, code="masking_film_tape", name="Masking film and tape", unit="pcs", package_size=Decimal("1"), price_ex_vat=Decimal("199"))

    _upsert_norm(db, work_type_code="PAINT_WALL", material=wall_paint, qty_per_basis=Decimal("0.23"), basis_type="m2", material_unit="l")
    _upsert_norm(db, work_type_code="PAINT_CEILING", material=ceiling_paint, qty_per_basis=Decimal("0.18"), basis_type="m2", material_unit="l")
    _upsert_norm(db, work_type_code="PRIMER_WALL", material=primer, qty_per_basis=Decimal("0.12"), basis_type="m2", material_unit="l")
    _upsert_norm(db, work_type_code="SKIM_WALL", material=spackle, qty_per_basis=Decimal("0.80"), basis_type="m2", material_unit="kg")
    _upsert_norm(db, work_type_code="SAND_WALL", material=sanding, qty_per_basis=Decimal("0.15"), basis_type="m2", material_unit="pcs")
    _upsert_norm(db, work_type_code="MASK_FLOOR", material=masking, qty_per_basis=Decimal("0.08"), basis_type="m2", material_unit="pcs")

    db.commit()


def main() -> None:
    db = SessionLocal()
    try:
        seed_defaults(db)
    finally:
        db.close()
    print("Default work types/materials/norms seeded.")


if __name__ == "__main__":
    main()
