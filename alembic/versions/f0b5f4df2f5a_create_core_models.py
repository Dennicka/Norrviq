"""create core models

Revision ID: f0b5f4df2f5a
Revises: 
Create Date: 2025-02-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f0b5f4df2f5a"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("contact_person", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_private_person", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_rot_eligible", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_clients_id"), "clients", ["id"], unique=False)

    op.create_table(
        "cost_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name_ru", sa.String(length=255), nullable=False),
        sa.Column("name_sv", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_cost_categories_id"), "cost_categories", ["id"], unique=False)

    op.create_table(
        "legal_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("title_ru", sa.String(length=255), nullable=False),
        sa.Column("text_ru", sa.Text(), nullable=False),
        sa.Column("title_sv", sa.String(length=255), nullable=False),
        sa.Column("text_sv", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_legal_notes_id"), "legal_notes", ["id"], unique=False)

    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hourly_rate_company", sa.Numeric(precision=10, scale=2), nullable=False, server_default=sa.text("550.00")),
        sa.Column(
            "default_worker_hourly_rate",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            server_default=sa.text("180.00"),
        ),
        sa.Column(
            "employer_contributions_percent",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default=sa.text("31.42"),
        ),
        sa.Column("moms_percent", sa.Numeric(precision=5, scale=2), nullable=False, server_default=sa.text("25.00")),
        sa.Column("rot_percent", sa.Numeric(precision=5, scale=2), nullable=False, server_default=sa.text("50.00")),
        sa.Column("fuel_price_per_liter", sa.Numeric(precision=10, scale=2), nullable=False, server_default=sa.text("20.00")),
        sa.Column("transport_cost_per_km", sa.Numeric(precision=10, scale=2), nullable=False, server_default=sa.text("25.00")),
        sa.Column("default_overhead_percent", sa.Numeric(precision=5, scale=2), nullable=False, server_default=sa.text("10.00")),
        sa.Column(
            "default_worker_tax_percent_for_net",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default=sa.text("30.00"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_settings_id"), "settings", ["id"], unique=False)

    op.create_table(
        "work_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("name_ru", sa.String(length=255), nullable=False),
        sa.Column("description_ru", sa.Text(), nullable=True),
        sa.Column("name_sv", sa.String(length=255), nullable=False),
        sa.Column("description_sv", sa.Text(), nullable=True),
        sa.Column("hours_per_unit", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("base_difficulty_factor", sa.Numeric(precision=5, scale=2), nullable=False, server_default=sa.text("1.0")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_work_types_id"), "work_types", ["id"], unique=False)

    op.create_table(
        "workers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=100), nullable=True),
        sa.Column("hourly_rate", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workers_id"), "workers", ["id"], unique=False)

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("use_rot", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("billing_status", sa.String(length=50), nullable=False, server_default="not_billed"),
        sa.Column("work_sum_without_moms", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("moms_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("rot_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("client_pays_total", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projects_id"), "projects", ["id"], unique=False)

    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("walls_area_m2", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("ceiling_area_m2", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("floor_area_m2", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("plinth_length_m", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rooms_id"), "rooms", ["id"], unique=False)

    op.create_table(
        "project_cost_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("cost_category_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("moms_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_material", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.ForeignKeyConstraint(["cost_category_id"], ["cost_categories.id"], ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_cost_items_id"), "project_cost_items", ["id"], unique=False)

    op.create_table(
        "project_work_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=True),
        sa.Column("work_type_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("difficulty_factor", sa.Numeric(precision=5, scale=2), nullable=False, server_default=sa.text("1.0")),
        sa.Column("calculated_hours", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("calculated_cost_without_moms", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ),
        sa.ForeignKeyConstraint(["work_type_id"], ["work_types.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_work_items_id"), "project_work_items", ["id"], unique=False)

    op.create_table(
        "project_worker_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.Integer(), nullable=False),
        sa.Column("planned_hours", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("actual_hours", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_worker_assignments_id"), "project_worker_assignments", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_project_worker_assignments_id"), table_name="project_worker_assignments")
    op.drop_table("project_worker_assignments")
    op.drop_index(op.f("ix_project_work_items_id"), table_name="project_work_items")
    op.drop_table("project_work_items")
    op.drop_index(op.f("ix_project_cost_items_id"), table_name="project_cost_items")
    op.drop_table("project_cost_items")
    op.drop_index(op.f("ix_rooms_id"), table_name="rooms")
    op.drop_table("rooms")
    op.drop_index(op.f("ix_projects_id"), table_name="projects")
    op.drop_table("projects")
    op.drop_index(op.f("ix_workers_id"), table_name="workers")
    op.drop_table("workers")
    op.drop_index(op.f("ix_work_types_id"), table_name="work_types")
    op.drop_table("work_types")
    op.drop_index(op.f("ix_settings_id"), table_name="settings")
    op.drop_table("settings")
    op.drop_index(op.f("ix_legal_notes_id"), table_name="legal_notes")
    op.drop_table("legal_notes")
    op.drop_index(op.f("ix_cost_categories_id"), table_name="cost_categories")
    op.drop_table("cost_categories")
    op.drop_index(op.f("ix_clients_id"), table_name="clients")
    op.drop_table("clients")
