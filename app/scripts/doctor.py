from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass

from app.services.pdf_renderer import is_playwright_available, is_weasyprint_available


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    hint: str | None = None


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def main() -> int:
    checks: list[Check] = []
    checks.append(Check("Python version", sys.version_info >= (3, 11), f"{sys.version.split()[0]}", "Use Python 3.11+"))
    checks.append(Check("venv active", bool(os.getenv("VIRTUAL_ENV")), os.getenv("VIRTUAL_ENV", "not active"), "source .venv/bin/activate"))
    db_url = os.getenv("DATABASE_URL", "sqlite:///./norrviq.db")
    checks.append(Check("DB URL", bool(db_url), db_url, "Set DATABASE_URL in .env"))

    heads = _run([sys.executable, "-m", "alembic", "heads"])
    heads_lines = [ln for ln in heads.stdout.splitlines() if ln.strip() and "(head)" in ln]
    checks.append(
        Check(
            "Alembic single head",
            heads.returncode == 0 and len(heads_lines) == 1,
            heads.stdout.strip() or heads.stderr.strip() or "no output",
            "Run migrations cleanup so `alembic heads` returns exactly one head.",
        )
    )

    weasy_ok = is_weasyprint_available()
    checks.append(Check("PDF WeasyPrint", weasy_ok, "available" if weasy_ok else "unavailable", "Install cairo/pango system libs or use Playwright backend."))
    playwright_ok = is_playwright_available()
    checks.append(
        Check(
            "PDF Playwright+Chromium",
            playwright_ok,
            "available" if playwright_ok else "unavailable",
            "Run `make pdf-install` (or `python -m playwright install chromium`).",
        )
    )

    print("Environment doctor")
    for item in checks:
        marker = "OK" if item.ok else "FAIL"
        print(f"[{marker}] {item.name}: {item.detail}")
        if not item.ok and item.hint:
            print(f"       hint: {item.hint}")

    failed = [c for c in checks if not c.ok]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
