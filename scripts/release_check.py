#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

MAX_FAILURE_LINES = 120


@dataclass
class StepResult:
    step: str
    command: str
    status: str
    duration_s: float
    output: str
    notes: str = ""


def _run_command(step: str, command: list[str]) -> StepResult:
    print(f"\n=== {step} ===")
    print("$", " ".join(command))
    started = time.monotonic()
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    duration = time.monotonic() - started
    output = (completed.stdout or "") + (completed.stderr or "")
    status = "PASS" if completed.returncode == 0 else "FAIL"
    notes = ""

    if step == "Doctor":
        status, notes = _doctor_gate_status(output, completed.returncode)

    print(f"{status} ({duration:.2f}s)")
    if status == "FAIL":
        lines = output.splitlines()
        tail = "\n".join(lines[-MAX_FAILURE_LINES:])
        print(f"--- Last {min(MAX_FAILURE_LINES, len(lines))} lines from failed step ---")
        print(tail)
        print("--- End of failure output ---")

    return StepResult(step=step, command=" ".join(command), status=status, duration_s=duration, output=output, notes=notes)


def _doctor_gate_status(output: str, returncode: int) -> tuple[str, str]:
    pattern = r"PDF:\s+configured=(\S+)\s+active=(\S+)\s+weasyprint=(\d)\s+playwright=(\d)"
    match = re.search(pattern, output)
    if not match:
        if returncode != 0:
            return "FAIL", "doctor failed and PDF capability line not found"
        return "PASS", "PDF capability line not found"

    configured, active, weasyprint, playwright = match.groups()
    notes = f"configured={configured}, active={active}, weasyprint={weasyprint}, playwright={playwright}"
    if configured == "weasyprint" and weasyprint == "0":
        return "FAIL", notes
    if configured == "playwright" and playwright == "0":
        return "FAIL", notes
    return "PASS", notes


def format_summary_table(results: list[StepResult]) -> str:
    headers = ("Step", "Status", "Duration", "Notes")
    rows = [(result.step, result.status, f"{result.duration_s:.2f}s", result.notes) for result in results]

    widths = [len(header) for header in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    def _fmt(values: tuple[str, str, str, str]) -> str:
        return " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(values))

    divider = "-+-".join("-" * width for width in widths)
    lines = [_fmt(headers), divider]
    lines.extend(_fmt(row) for row in rows)
    return "\n".join(lines)


def _has_acceptance_marker() -> bool:
    pytest_ini = Path("pytest.ini")
    if not pytest_ini.exists():
        return False
    return "acceptance:" in pytest_ini.read_text(encoding="utf-8")


def main() -> int:
    acceptance_cmd = ["pytest", "-q", "-m", "acceptance"]
    if not _has_acceptance_marker():
        acceptance_cmd = ["pytest", "-q", "tests/acceptance/test_acceptance_pack.py"]

    steps = [
        ("Lint", ["ruff", "check", "."]),
        ("DB migrations sanity", ["pytest", "-q", "tests/test_alembic_single_head.py", "tests/test_db_migrations.py"]),
        ("Regression suite", ["pytest", "-q", "tests/regression/test_golden_regression.py"]),
        ("Acceptance pack", acceptance_cmd),
        ("Doctor", [sys.executable, "-m", "app.scripts.doctor"]),
    ]

    results = [_run_command(step, command) for step, command in steps]

    print("\n=== Release readiness summary ===")
    print(format_summary_table(results))

    failed_steps = [result.step for result in results if result.status != "PASS"]
    if failed_steps:
        print(f"\nOVERALL: FAIL ({', '.join(failed_steps)})")
        return 1

    print("\nOVERALL: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
