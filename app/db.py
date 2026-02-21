from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_schema_up_to_date() -> None:
    """Verify that DB schema has an Alembic revision at head."""
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    expected_heads = set(script.get_heads())

    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        current_heads = set(context.get_current_heads())

    if current_heads != expected_heads:
        raise RuntimeError(
            "Database schema is out of date. Run 'alembic upgrade head' and restart the application."
        )
