from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import SessionLocal  # noqa: E402
from tests.regression.golden_data import GOLDEN_CASES, render_case_snapshot, write_golden  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        for case_name in GOLDEN_CASES:
            snapshot = render_case_snapshot(db, case_name)
            write_golden(case_name, snapshot)
            print(f"updated tests/golden/{case_name}.json")
    finally:
        db.close()


if __name__ == "__main__":
    main()
