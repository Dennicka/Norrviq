from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.client import Client
from app.models.company_profile import get_or_create_company_profile
from app.models.invoice import Invoice
from app.models.material import Material
from app.models.material_catalog_item import MaterialCatalogItem
from app.models.material_norm import MaterialConsumptionNorm
from app.models.cost import CostCategory, ProjectCostItem
from app.models.pricing_policy import get_or_create_pricing_policy
from app.models.project import Project, ProjectWorkItem
from app.models.project_pricing import ProjectPricing
from app.models.project_takeoff_settings import ProjectTakeoffSettings
from app.models.room import Room
from app.models.supplier import Supplier
from app.models.supplier_material_price import SupplierMaterialPrice
from app.models.worktype import WorkType
from app.services.commercial_snapshot import DOC_TYPE_OFFER, read_commercial_snapshot
from app.services.invoice_lines import generate_invoice_lines_from_project, recalculate_invoice_totals
from app.services.materials_bom import ProcurementStrategy, compute_procurement_plan, compute_project_bom
from app.services.pricing import (
    FLOOR_REASON_EFFECTIVE_HOURLY_BELOW_MIN,
    compute_pricing_scenarios,
    evaluate_floor,
)
from app.services.pricing_sanity import safe_effective_hourly_rate
from app.services.shopping_list import compute_project_shopping_list
from app.services.work_scope_apply import build_scope_preview
from app.services.document_numbering import finalize_offer
from app.services.procurement_rounding import ProcurementRoundingPolicy


client = TestClient(app)
settings = get_settings()
Q = Decimal("0.01")


@dataclass
class ScenarioProject:
    project_id: int
    client_id: int


class AcceptanceBuilder:
    def __init__(self) -> None:
        self.db = SessionLocal()

    def close(self) -> None:
        self.db.close()

    def create_project(self, *, name_prefix: str, m2_basis: str = "FLOOR_AREA", include_openings_subtraction: bool = False) -> ScenarioProject:
        profile = get_or_create_company_profile(self.db)
        profile.legal_name = "Acceptance Bygg AB"

        client_obj = Client(
            name=f"Client-{uuid4().hex[:8]}",
            email=f"acceptance-{uuid4().hex[:6]}@example.com",
            client_segment="B2C",
            is_private_person=True,
            is_rot_eligible=True,
        )
        self.db.add(client_obj)
        self.db.flush()

        project = Project(name=f"{name_prefix}-{uuid4().hex[:8]}", client_id=client_obj.id)
        self.db.add(project)
        self.db.flush()

        self.db.add(
            ProjectTakeoffSettings(
                project_id=project.id,
                m2_basis=m2_basis,
                include_openings_subtraction=include_openings_subtraction,
            )
        )
        self.db.add(ProjectPricing(project_id=project.id, mode="HOURLY"))
        self.db.commit()
        return ScenarioProject(project_id=project.id, client_id=client_obj.id)

    def add_room(
        self,
        *,
        project_id: int,
        name: str,
        floor: Decimal,
        wall_area: Decimal | None = None,
        ceiling: Decimal | None = None,
        perimeter: Decimal | None = None,
        height: Decimal | None = None,
        openings: Decimal | None = None,
    ) -> Room:
        room = Room(
            project_id=project_id,
            name=name,
            floor_area_m2=floor,
            wall_area_m2=wall_area,
            ceiling_area_m2=ceiling,
            wall_perimeter_m=perimeter,
            wall_height_m=height,
            openings_area_m2=openings,
        )
        self.db.add(room)
        self.db.flush()
        return room

    def add_work_item(
        self,
        *,
        project_id: int,
        room_id: int,
        work_code: str,
        quantity: Decimal,
        hours_per_unit: Decimal,
        unit: str = "m2",
        category: str = "wall",
    ) -> ProjectWorkItem:
        work_type = WorkType(
            code=f"{work_code}-{uuid4().hex[:5]}",
            category=category,
            unit=unit,
            name_ru="Работа",
            name_sv="Arbete",
            hours_per_unit=hours_per_unit,
            base_difficulty_factor=Decimal("1"),
            is_active=True,
        )
        self.db.add(work_type)
        self.db.flush()

        hours = (quantity * hours_per_unit).quantize(Q)
        item = ProjectWorkItem(
            project_id=project_id,
            room_id=room_id,
            work_type_id=work_type.id,
            quantity=quantity,
            difficulty_factor=Decimal("1"),
            calculated_hours=hours,
            norm_hours_per_unit=hours_per_unit,
        )
        self.db.add(item)
        self.db.flush()
        return item


def _login() -> None:
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def _totals_for(project_id: int):
    db = SessionLocal()
    try:
        baseline, scenarios = compute_pricing_scenarios(db, project_id)
        bom = compute_project_bom(db, project_id)
        shopping = compute_project_shopping_list(db, project_id, include_items_without_price=True)
        return baseline, scenarios, bom, shopping
    finally:
        db.close()


@pytest.mark.acceptance
def test_scenario_a_single_room_openings_per_m2_paintable_basis():
    builder = AcceptanceBuilder()
    try:
        scenario = builder.create_project(name_prefix="A", m2_basis="PAINTABLE_TOTAL", include_openings_subtraction=True)
        room = builder.add_room(
            project_id=scenario.project_id,
            name="Living",
            floor=Decimal("12.00"),
            perimeter=Decimal("14.00"),
            height=Decimal("2.50"),
            openings=Decimal("4.80"),
        )
        builder.add_work_item(
            project_id=scenario.project_id,
            room_id=room.id,
            work_code="PAINT-A",
            quantity=Decimal("1.00"),
            hours_per_unit=Decimal("8.00"),
        )
        pricing = builder.db.query(ProjectPricing).filter_by(project_id=scenario.project_id).one()
        pricing.mode = "PER_M2"
        pricing.rate_per_m2 = Decimal("100.00")
        builder.db.commit()

        baseline, scenarios, _bom, _shopping = _totals_for(scenario.project_id)

        expected_wall = (Decimal("14.00") * Decimal("2.50") - Decimal("4.80")).quantize(Q)
        expected_total = (expected_wall + Decimal("12.00")).quantize(Q)
        assert baseline.total_m2 == expected_total

        per_m2 = next(s for s in scenarios if s.mode == "PER_M2")
        assert per_m2.price_ex_vat == (baseline.total_m2 * Decimal("100.00")).quantize(Q)

        _login()
        offer_print = client.get(f"/offers/{scenario.project_id}/print?lang=sv")
        assert offer_print.status_code == 200
        assert "Offert" in offer_print.text
        assert ("Moms" in offer_print.text) or ("MOMS" in offer_print.text)
        assert ("Totalt" in offer_print.text) or ("Total" in offer_print.text) or ("Att betala" in offer_print.text)

        offer_pdf = client.get(f"/offers/{scenario.project_id}/pdf")
        assert offer_pdf.status_code == 200
        assert offer_pdf.headers["content-type"] == "application/pdf"
        assert offer_pdf.content.startswith(b"%PDF")
    finally:
        builder.close()


@pytest.mark.acceptance
def test_scenario_b_apartment_selected_rooms_scope():
    builder = AcceptanceBuilder()
    try:
        scenario = builder.create_project(name_prefix="B", m2_basis="WALL_AREA")
        room1 = builder.add_room(project_id=scenario.project_id, name="R1", floor=Decimal("9"), wall_area=Decimal("20.00"))
        room2 = builder.add_room(project_id=scenario.project_id, name="R2", floor=Decimal("10"), wall_area=Decimal("15.00"))
        room3 = builder.add_room(project_id=scenario.project_id, name="R3", floor=Decimal("8"), wall_area=Decimal("18.00"))

        item = builder.add_work_item(
            project_id=scenario.project_id,
            room_id=room1.id,
            work_code="PAINT-B",
            quantity=Decimal("1.00"),
            hours_per_unit=Decimal("5.00"),
        )

        project = builder.db.get(Project, scenario.project_id)
        wt = builder.db.get(WorkType, item.work_type_id)
        preview = build_scope_preview(
            project=project,
            work_type=wt,
            scope_apply_mode="selected_rooms",
            room_ids=[room1.id, room3.id],
            basis_type="wall_area_m2",
        )
        expected_qty = Decimal("38.00")
        assert preview.estimated_quantity == expected_qty
        assert not any("INCOMPLETE_GEOMETRY" in warning for warning in preview.warnings)

        item.quantity = expected_qty
        item.calculated_hours = (expected_qty * Decimal("0.20")).quantize(Q)
        builder.db.commit()

        baseline, _scenarios, _bom, _shopping = _totals_for(scenario.project_id)
        assert item.quantity == expected_qty
        assert baseline.labor_hours_total > 0
        assert room2.wall_area_m2 == Decimal("15.00")
    finally:
        builder.close()


@pytest.mark.acceptance
def test_scenario_c_hourly_floor_uses_hourly_rate_even_with_big_materials():
    builder = AcceptanceBuilder()
    try:
        scenario = builder.create_project(name_prefix="C", m2_basis="WALL_AREA")
        room = builder.add_room(project_id=scenario.project_id, name="R", floor=Decimal("20"), wall_area=Decimal("40"))
        builder.add_work_item(
            project_id=scenario.project_id,
            room_id=room.id,
            work_code="PAINT-C",
            quantity=Decimal("10.00"),
            hours_per_unit=Decimal("1.00"),
        )
        material = Material(code=f"MAT-C-{uuid4().hex[:5]}", name_sv="C Paint", name_ru="Краска C", unit="L", is_active=True)
        builder.db.add(material)
        builder.db.flush()

        catalog = MaterialCatalogItem(
            material_code=material.code,
            name="Premium Paint",
            unit="L",
            package_size=Decimal("10"),
            package_unit="L",
            price_ex_vat=Decimal("1500"),
            supplier_name="Catalog Supplier",
            is_default_for_material=True,
            is_active=True,
        )
        builder.db.add(catalog)
        builder.db.flush()
        wt = builder.db.query(WorkType).join(ProjectWorkItem, ProjectWorkItem.work_type_id == WorkType.id).filter(ProjectWorkItem.project_id == scenario.project_id).first()
        builder.db.add(
            MaterialConsumptionNorm(
                active=True,
                applies_to_work_type=wt.code,
                material_catalog_item_id=catalog.id,
                material_name="Premium Paint",
                material_category="paint",
                material_unit="L",
                surface_type="wall",
                consumption_value=Decimal("1.00"),
                consumption_unit="per_1_m2",
                waste_percent=Decimal("0"),
                layers_multiplier_enabled=False,
                coats_multiplier_mode="none",
            )
        )

        pricing = builder.db.query(ProjectPricing).filter_by(project_id=scenario.project_id).one()
        pricing.mode = "HOURLY"
        pricing.hourly_rate_override = Decimal("600.00")
        pricing.include_materials = True
        materials_category = builder.db.query(CostCategory).filter_by(code="MATERIALS").first()
        if materials_category is None:
            materials_category = CostCategory(code="MATERIALS", name_ru="Материалы", name_sv="Material")
            builder.db.add(materials_category)
            builder.db.flush()
        builder.db.add(
            ProjectCostItem(
                project_id=scenario.project_id,
                cost_category_id=materials_category.id,
                title="Extra materials",
                amount=Decimal("5000.00"),
                is_material=True,
            )
        )

        policy = get_or_create_pricing_policy(builder.db)
        policy.min_effective_hourly_ex_vat = Decimal("700.00")
        builder.db.commit()

        baseline, scenarios, _bom, _shopping = _totals_for(scenario.project_id)
        hourly = next(s for s in scenarios if s.mode == "HOURLY")
        floor = evaluate_floor(baseline, hourly, policy)

        assert floor.is_below_floor is True
        assert any(reason.code == FLOOR_REASON_EFFECTIVE_HOURLY_BELOW_MIN for reason in floor.reasons)
        assert Decimal(str(hourly.input_params["hourly_rate"])) == Decimal("600.00")
        effective_hourly, _issues = safe_effective_hourly_rate(hourly.price_ex_vat, baseline.labor_hours_total)
        assert effective_hourly is not None and effective_hourly >= Decimal("700.00")

        _login()
        apply_best = client.post(
            f"/projects/{scenario.project_id}/pricing",
            data={"intent": "apply_best_mode", "best_metric": "profit"},
            follow_redirects=False,
        )
        assert apply_best.status_code == 303

        baseline2, scenarios2 = compute_pricing_scenarios(builder.db, scenario.project_id)
        selected_mode = builder.db.query(ProjectPricing).filter_by(project_id=scenario.project_id).one().mode
        selected = next(s for s in scenarios2 if s.mode == selected_mode)
        selected_floor = evaluate_floor(baseline2, selected, policy)
        if selected_floor.is_below_floor:
            assert any(reason.code == FLOOR_REASON_EFFECTIVE_HOURLY_BELOW_MIN for reason in floor.reasons)
    finally:
        builder.close()


@pytest.mark.acceptance
def test_scenario_d_material_mapping_and_catalog_fallback_rounding_ceil():
    builder = AcceptanceBuilder()
    try:
        scenario = builder.create_project(name_prefix="D", m2_basis="WALL_AREA")
        room = builder.add_room(project_id=scenario.project_id, name="R", floor=Decimal("10"), wall_area=Decimal("20"))
        item = builder.add_work_item(
            project_id=scenario.project_id,
            room_id=room.id,
            work_code="PAINT-D",
            quantity=Decimal("1.00"),
            hours_per_unit=Decimal("4.00"),
        )

        material = Material(code=f"MAT-D-{uuid4().hex[:5]}", name_sv="Paint D", name_ru="Краска D", unit="L", is_active=True)
        builder.db.add(material)
        builder.db.flush()
        catalog = MaterialCatalogItem(
            material_code=material.code,
            name="Paint D 10L",
            unit="L",
            package_size=Decimal("10"),
            package_unit="L",
            price_ex_vat=Decimal("100"),
            supplier_name="Catalog Supplier",
            is_default_for_material=True,
            is_active=True,
        )
        builder.db.add(catalog)
        builder.db.flush()
        wt = builder.db.get(WorkType, item.work_type_id)

        builder.db.add(
            MaterialConsumptionNorm(
                active=True,
                applies_to_work_type=wt.code,
                material_catalog_item_id=catalog.id,
                material_name="Paint D",
                material_category="paint",
                material_unit="L",
                surface_type="wall",
                consumption_value=Decimal("1.05"),
                consumption_unit="per_1_m2",
                waste_percent=Decimal("0"),
                layers_multiplier_enabled=False,
                coats_multiplier_mode="none",
            )
        )
        builder.db.commit()

        _baseline, _scenarios, bom, shopping = _totals_for(scenario.project_id)
        assert bom.items[0].material_id > 0

        row = shopping.items[0]
        assert row.supplier_name == "Catalog Supplier"
        assert "CATALOG_PRICE_USED" in row.warnings
        assert row.packs_needed == Decimal("3")
    finally:
        builder.close()


@pytest.mark.acceptance
def test_scenario_e_supplier_price_beats_catalog_with_pack_multiple_policy():
    builder = AcceptanceBuilder()
    try:
        scenario = builder.create_project(name_prefix="E", m2_basis="WALL_AREA")
        room = builder.add_room(project_id=scenario.project_id, name="R", floor=Decimal("10"), wall_area=Decimal("20"))
        item = builder.add_work_item(
            project_id=scenario.project_id,
            room_id=room.id,
            work_code="PAINT-E",
            quantity=Decimal("1.00"),
            hours_per_unit=Decimal("4.00"),
        )

        material = Material(code=f"MAT-E-{uuid4().hex[:5]}", name_sv="Paint E", name_ru="Краска E", unit="L", is_active=True)
        builder.db.add(material)
        builder.db.flush()

        catalog = MaterialCatalogItem(
            material_code=material.code,
            name="Paint E 10L",
            unit="L",
            package_size=Decimal("10"),
            package_unit="L",
            price_ex_vat=Decimal("120"),
            supplier_name="Catalog Supplier",
            is_default_for_material=True,
            is_active=True,
        )
        builder.db.add(catalog)
        builder.db.flush()
        wt = builder.db.get(WorkType, item.work_type_id)

        builder.db.add(
            MaterialConsumptionNorm(
                active=True,
                applies_to_work_type=wt.code,
                material_catalog_item_id=catalog.id,
                material_name="Paint E",
                material_category="paint",
                material_unit="L",
                surface_type="wall",
                consumption_value=Decimal("1.05"),
                consumption_unit="per_1_m2",
                waste_percent=Decimal("0"),
                layers_multiplier_enabled=False,
                coats_multiplier_mode="none",
            )
        )

        supplier = Supplier(name=f"Supplier-{uuid4().hex[:5]}", is_active=True)
        builder.db.add(supplier)
        builder.db.flush()
        builder.db.add(
            SupplierMaterialPrice(
                supplier_id=supplier.id,
                material_id=material.id,
                pack_size=Decimal("10"),
                pack_unit="L",
                pack_price_ex_vat=Decimal("80"),
                currency="SEK",
            )
        )
        builder.db.commit()

        _baseline, _scenarios, _bom, _shopping = _totals_for(scenario.project_id)
        plan = compute_procurement_plan(
            builder.db,
            scenario.project_id,
            strategy=ProcurementStrategy.CHEAPEST,
            policy=ProcurementRoundingPolicy(rounding_mode="CEIL", pack_multiple=2),
        )
        line = plan.lines[0]

        assert line.unit_price_ex_vat == Decimal("80")
        assert line.packs_needed == Decimal("4")
        assert int(line.packs_needed) % 2 == 0
    finally:
        builder.close()


@pytest.mark.acceptance
def test_scenario_f_documents_freeze_and_multilingual_prints():
    builder = AcceptanceBuilder()
    try:
        scenario = builder.create_project(name_prefix="F", m2_basis="WALL_AREA")
        room = builder.add_room(project_id=scenario.project_id, name="R", floor=Decimal("12"), wall_area=Decimal("24"))
        item = builder.add_work_item(
            project_id=scenario.project_id,
            room_id=room.id,
            work_code="PAINT-F",
            quantity=Decimal("5.00"),
            hours_per_unit=Decimal("1.00"),
        )

        pricing = builder.db.query(ProjectPricing).filter_by(project_id=scenario.project_id).one()
        pricing.mode = "HOURLY"
        pricing.hourly_rate_override = Decimal("650.00")

        invoice = Invoice(
            project_id=scenario.project_id,
            issue_date=date(2024, 1, 1),
            status="draft",
            work_sum_without_moms=Decimal("0"),
            moms_amount=Decimal("0"),
            rot_amount=Decimal("0"),
            client_pays_total=Decimal("0"),
            document_lang="ru",
        )
        builder.db.add(invoice)
        builder.db.flush()
        invoice_id = invoice.id
        generate_invoice_lines_from_project(builder.db, project_id=scenario.project_id, invoice_id=invoice_id)
        recalculate_invoice_totals(builder.db, invoice_id, user_id="acceptance")
        builder.db.commit()

        db2 = SessionLocal()
        try:
            policy = get_or_create_pricing_policy(db2)
            policy.min_margin_pct = Decimal("0")
            policy.min_profit_sek = Decimal("0")
            policy.min_effective_hourly_ex_vat = Decimal("0")
            policy.block_issue_below_floor = False
            db2.commit()

            profile = get_or_create_company_profile(db2)
            finalize_offer(db2, scenario.project_id, user_id="acceptance", profile=profile, lang="en")
            db2.commit()

            snapshot_before = read_commercial_snapshot(db2, doc_type=DOC_TYPE_OFFER, doc_id=scenario.project_id)
            frozen_total = Decimal(str(snapshot_before["totals"]["price_inc_vat"])).quantize(Q)

            item2 = db2.get(ProjectWorkItem, item.id)
            pricing2 = db2.query(ProjectPricing).filter_by(project_id=scenario.project_id).one()
            item2.quantity = Decimal("12.00")
            item2.calculated_hours = Decimal("12.00")
            pricing2.hourly_rate_override = Decimal("999.00")
            db2.commit()

            snapshot_after = read_commercial_snapshot(db2, doc_type=DOC_TYPE_OFFER, doc_id=scenario.project_id)
            assert Decimal(str(snapshot_after["totals"]["price_inc_vat"])).quantize(Q) == frozen_total
        finally:
            db2.close()

        _baseline, _scenarios, _bom, _shopping = _totals_for(scenario.project_id)

        _login()
        offer_print = client.get(f"/offers/{scenario.project_id}/print?lang=en")
        assert offer_print.status_code == 200
        assert "Offer" in offer_print.text
        assert "VAT" in offer_print.text
        assert "Total" in offer_print.text

        invoice_print = client.get(f"/invoices/{invoice_id}/print?lang=ru")
        assert invoice_print.status_code == 200
        assert ("Счет" in invoice_print.text) or ("Счёт" in invoice_print.text)
        assert "НДС" in invoice_print.text
        assert "Итого" in invoice_print.text
    finally:
        builder.close()
