from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import relationship

from app.db import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    name = Column(String(255), nullable=False)
    address = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    status = Column(String(50), nullable=False, default="draft")
    planned_start_date = Column(Date, nullable=True)
    planned_end_date = Column(Date, nullable=True)
    actual_start_date = Column(Date, nullable=True)
    actual_end_date = Column(Date, nullable=True)
    use_rot = Column(Boolean, nullable=False, default=False)
    billing_status = Column(String(50), nullable=False, default="not_billed")
    offer_status = Column(String(20), nullable=False, default="draft")
    offer_number = Column(String(64), unique=True, index=True, nullable=True)
    offer_terms_snapshot_title = Column(Text, nullable=True)
    offer_terms_snapshot_body = Column(Text, nullable=True)
    offer_commercial_snapshot = Column(Text, nullable=True)
    work_sum_without_moms = Column(Numeric(12, 2), nullable=True)
    moms_amount = Column(Numeric(12, 2), nullable=True)
    rot_amount = Column(Numeric(12, 2), nullable=True)
    client_pays_total = Column(Numeric(12, 2), nullable=True)

    salary_fund = Column(Numeric(12, 2), nullable=True)
    employer_taxes = Column(Numeric(12, 2), nullable=True)
    total_salary_cost = Column(Numeric(12, 2), nullable=True)

    materials_cost = Column(Numeric(12, 2), nullable=True)
    fuel_cost = Column(Numeric(12, 2), nullable=True)
    parking_cost = Column(Numeric(12, 2), nullable=True)
    rent_cost = Column(Numeric(12, 2), nullable=True)
    other_cost = Column(Numeric(12, 2), nullable=True)

    overhead_amount = Column(Numeric(12, 2), nullable=True)

    total_cost = Column(Numeric(12, 2), nullable=True)
    profit = Column(Numeric(12, 2), nullable=True)
    margin_percent = Column(Numeric(6, 2), nullable=True)

    client = relationship("Client", back_populates="projects")
    rooms = relationship("Room", back_populates="project", cascade="all, delete-orphan")
    work_items = relationship("ProjectWorkItem", back_populates="project", cascade="all, delete-orphan")
    worker_assignments = relationship(
        "ProjectWorkerAssignment", back_populates="project", cascade="all, delete-orphan"
    )
    cost_items = relationship("ProjectCostItem", back_populates="project", cascade="all, delete-orphan")
    invoices = relationship(
        "Invoice",
        back_populates="project",
        cascade="all, delete-orphan",
        foreign_keys="Invoice.project_id",
    )
    pricing = relationship(
        "ProjectPricing",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
    )
    buffer_settings = relationship(
        "ProjectBufferSettings",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
    )
    execution_profile = relationship(
        "ProjectExecutionProfile",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
    )

    takeoff_settings = relationship(
        "ProjectTakeoffSettings",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
    )
    material_settings = relationship(
        "ProjectMaterialSettings",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
    )
    paint_settings = relationship(
        "ProjectPaintSettings",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
    )
    procurement_settings = relationship(
        "ProjectProcurementSettings",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ProjectWorkItem(Base):
    __tablename__ = "project_work_items"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=True)
    work_type_id = Column(Integer, ForeignKey("work_types.id"), nullable=False)
    quantity = Column(Numeric(10, 2), nullable=False)
    difficulty_factor = Column(Numeric(5, 2), nullable=False, default=1.0)
    calculated_hours = Column(Numeric(10, 2), nullable=True)
    calculated_cost_without_moms = Column(Numeric(12, 2), nullable=True)
    pricing_mode = Column(String(20), nullable=False, default="hourly")
    hourly_rate_sek = Column(Numeric(10, 2), nullable=True)
    area_rate_sek = Column(Numeric(10, 2), nullable=True)
    fixed_price_sek = Column(Numeric(12, 2), nullable=True)
    billable_area_m2 = Column(Numeric(10, 2), nullable=True)
    labor_cost_sek = Column(Numeric(12, 2), nullable=True)
    materials_cost_sek = Column(Numeric(12, 2), nullable=True)
    total_cost_sek = Column(Numeric(12, 2), nullable=True)
    margin_sek = Column(Numeric(12, 2), nullable=True)
    margin_pct = Column(Numeric(6, 2), nullable=True)
    comment = Column(Text, nullable=True)

    project = relationship("Project", back_populates="work_items")
    room = relationship("Room", back_populates="work_items")
    work_type = relationship("WorkType", back_populates="project_work_items")


class ProjectWorkerAssignment(Base):
    __tablename__ = "project_worker_assignments"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=False)
    planned_hours = Column(Numeric(10, 2), nullable=True)
    actual_hours = Column(Numeric(10, 2), nullable=True)

    project = relationship("Project", back_populates="worker_assignments")
    worker = relationship("Worker", back_populates="assignments")
