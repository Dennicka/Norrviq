from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.db import SessionLocal
from app.models.client import Client
from app.models.company_profile import get_or_create_company_profile
from app.models.invoice import Invoice
from app.models.project import Project, ProjectWorkItem
from app.models.project_pricing import ProjectPricing
from app.models.project_takeoff_settings import ProjectTakeoffSettings
from app.models.room import Room
from app.models.rot_case import RotCase
from app.models.settings import get_or_create_settings
from app.models.worktype import WorkType
from app.services.document_numbering import finalize_invoice, finalize_offer
from app.services.invoice_lines import generate_invoice_lines_from_project, recalculate_invoice_totals


@dataclass(frozen=True)
class DocumentFixture:
    project_id: int
    invoice_id: int


def create_stable_document_fixture(*, enable_rot: bool, issue_documents: bool, pricing_mode: str = "HOURLY") -> DocumentFixture:
    db = SessionLocal()
    try:
        settings = get_or_create_settings(db)
        settings.hourly_rate_company = Decimal("550.00")
        settings.moms_percent = Decimal("25.00")
        settings.rot_percent = Decimal("30.00")

        profile = get_or_create_company_profile(db)
        profile.legal_name = "Trenor Måleri AB"
        profile.org_number = "556000-1234"
        profile.address_line1 = "Storgatan 1"
        profile.postal_code = "11122"
        profile.city = "Stockholm"
        profile.country = "Sverige"
        profile.email = "info@trenor.se"
        profile.phone = "08-123456"
        profile.bankgiro = "123-4567"

        customer = Client(
            name="Anna Andersson",
            address="Kundvägen 5",
            is_private_person=True,
            is_rot_eligible=True,
            client_segment="B2C",
            email="anna@example.com",
        )
        db.add(customer)
        db.flush()

        project = Project(
            name=f"Snapshot Project {pricing_mode}",
            address="Byggvägen 9",
            client_id=customer.id,
            use_rot=enable_rot,
            offer_status="draft",
        )
        db.add(project)
        db.flush()

        db.add(ProjectTakeoffSettings(project_id=project.id, m2_basis="PAINTABLE_TOTAL"))

        room = Room(project_id=project.id, name="Vardagsrum", floor_area_m2=Decimal("20.00"), wall_perimeter_m=Decimal("18.00"), wall_height_m=Decimal("2.50"))
        db.add(room)
        db.flush()

        work_type = WorkType(
            code=f"SNAP-{project.id}",
            category="paint",
            unit="h",
            name_ru="Покраска стен",
            name_sv="Målning väggar",
            hours_per_unit=Decimal("1.50"),
            base_difficulty_factor=Decimal("1.00"),
        )
        db.add(work_type)
        db.flush()

        db.add(
            ProjectWorkItem(
                project_id=project.id,
                room_id=room.id,
                work_type_id=work_type.id,
                quantity=Decimal("8.00"),
                difficulty_factor=Decimal("1.00"),
                calculated_hours=Decimal("12.00"),
                calculated_cost_without_moms=Decimal("6600.00"),
            )
        )

        pricing = ProjectPricing(project_id=project.id, mode=pricing_mode, hourly_rate_override=Decimal("550.00"), fixed_total_price=Decimal("7150.00"), rate_per_m2=Decimal("357.50"), rate_per_room=Decimal("7150.00"), rate_per_piece=Decimal("7150.00"))
        db.add(pricing)

        invoice = Invoice(
            project_id=project.id,
            issue_date=date(2024, 1, 20),
            status="draft",
            work_sum_without_moms=Decimal("0.00"),
            moms_amount=Decimal("0.00"),
            rot_amount=Decimal("0.00"),
            client_pays_total=Decimal("0.00"),
        )
        db.add(invoice)
        db.flush()

        generate_invoice_lines_from_project(db, project_id=project.id, invoice_id=invoice.id)

        rot_case = RotCase(invoice_id=invoice.id, is_enabled=enable_rot, rot_pct=Decimal("30.00"))
        db.add(rot_case)

        recalculate_invoice_totals(db, invoice.id, user_id="snapshot-tests")
        db.commit()

        if issue_documents:
            finalize_offer(db, project.id, user_id="snapshot-tests", profile=profile, lang="sv")
            finalize_invoice(db, invoice.id, user_id="snapshot-tests", profile=profile, lang="sv")

        db.commit()
        return DocumentFixture(project_id=project.id, invoice_id=invoice.id)
    finally:
        db.close()
