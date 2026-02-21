from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

from app.db import SessionLocal
from tests.regression.golden_data import GOLDEN_CASES, load_golden, render_case_snapshot

MAX_LARGE_CASE_SECONDS = Decimal("2.50")


IGNORED_PATHS = {"performance.compute_seconds"}


def _walk_diffs(expected, actual, path: str = "") -> Iterator[str]:
    if isinstance(expected, dict) and isinstance(actual, dict):
        all_keys = sorted(set(expected.keys()) | set(actual.keys()))
        for key in all_keys:
            next_path = f"{path}.{key}" if path else key
            if key not in expected:
                yield f"+ {next_path}: {actual[key]!r}"
                continue
            if key not in actual:
                yield f"- {next_path}: {expected[key]!r}"
                continue
            yield from _walk_diffs(expected[key], actual[key], next_path)
        return

    if isinstance(expected, list) and isinstance(actual, list):
        max_len = max(len(expected), len(actual))
        for idx in range(max_len):
            next_path = f"{path}[{idx}]"
            if idx >= len(expected):
                yield f"+ {next_path}: {actual[idx]!r}"
                continue
            if idx >= len(actual):
                yield f"- {next_path}: {expected[idx]!r}"
                continue
            yield from _walk_diffs(expected[idx], actual[idx], next_path)
        return

    if path in IGNORED_PATHS:
        return

    if expected != actual:
        yield f"~ {path}: expected={expected!r} actual={actual!r}"


def test_golden_regression_snapshots_match() -> None:
    db = SessionLocal()
    try:
        for case_name in GOLDEN_CASES:
            actual = render_case_snapshot(db, case_name)
            expected = load_golden(case_name)
            diffs = list(_walk_diffs(expected, actual))
            assert not diffs, f"Golden mismatch for {case_name}:\n" + "\n".join(diffs)

            if case_name == "g4_large":
                elapsed = Decimal(actual["performance"]["compute_seconds"])
                assert elapsed < MAX_LARGE_CASE_SECONDS, (
                    f"Large golden case is too slow: {elapsed}s >= {MAX_LARGE_CASE_SECONDS}s"
                )
    finally:
        db.close()
