from pathlib import Path

from sqlalchemy import create_engine, text

from app.db import ensure_schema_up_to_date
from tests.db_utils import upgrade_database


def test_no_create_all_usage():
    app_root = Path(__file__).resolve().parents[1] / "app"
    offenders: list[str] = []
    for py_file in app_root.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if "create_all(" in content:
            offenders.append(str(py_file.relative_to(app_root.parent)))
    assert offenders == []


def test_migrations_apply_clean_db(tmp_path: Path):
    db_path = tmp_path / "migration_check.sqlite3"
    db_url = f"sqlite:///{db_path}"

    upgrade_database(db_url)

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar() == 1

    ensure_schema_up_to_date()
