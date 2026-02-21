import os
from pathlib import Path

from alembic import command
from alembic.config import Config
import sqlalchemy as sa

from app.db import Base

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def upgrade_database(database_url: str) -> None:
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", database_url)
        command.upgrade(cfg, "head")
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url


def clear_database(session, *, exclude_tables: set[str] | None = None) -> None:
    """Delete rows from all mapped tables in FK-safe order (children -> parents)."""
    skipped = exclude_tables or set()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in skipped:
            continue
        session.execute(sa.delete(table))
    session.commit()


def clear_selected_tables(session, table_names: set[str]) -> None:
    """Delete only selected tables in FK-safe order (children -> parents)."""
    for table in reversed(Base.metadata.sorted_tables):
        if table.name not in table_names:
            continue
        session.execute(sa.delete(table))
    session.commit()
