from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.engine import Engine


class SQLCounter:
    def __init__(self) -> None:
        self.total = 0


@contextmanager
def count_sql_statements(engine: Engine) -> Iterator[SQLCounter]:
    counter = SQLCounter()

    def _before_cursor_execute(_conn, _cursor, statement, _parameters, _context, _executemany):
        sql = (statement or "").strip().upper()
        if sql.startswith(("SELECT", "INSERT", "UPDATE", "DELETE")):
            counter.total += 1

    event.listen(engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _before_cursor_execute)
