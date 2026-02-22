# Performance tests

## What is covered

`tests/perf/test_large_project_perf.py` creates a deterministic large project with:

- 50 rooms
- 300 work items
- project buffers enabled
- MEDIUM speed profile
- HOURLY pricing mode

The perf pipeline test measures:

- `compute_pricing_scenarios` (baseline + scenarios)
- `evaluate_floor`
- `compute_completeness`
- `evaluate_project_quality`
- end-to-end pipeline timing
- SQL query count guard

The UI stress safety test verifies for the same project:

- `GET /projects/{id}`
- `GET /projects/{id}/pricing`
- `GET /projects/{id}/invoices/{invoice_id}` for a draft invoice

## Local run

Run only perf tests:

```bash
RUN_PERF_TESTS=1 pytest -m perf -q
```

Skip perf tests (default behavior):

```bash
pytest -q
```

Generate a large project manually:

```bash
python scripts/generate_large_project.py --rooms 50 --items 300
```

## Current thresholds

- baseline computation: `< 2.0s`
- pricing scenarios computation: `< 2.0s`
- full pipeline: `< 6.0s`
- each UI page response: `< 3.0s`
- SQL query count for pipeline: `<= 2000`

Thresholds are intentionally lenient to avoid flaky runs on shared CI hardware while still catching major regressions.

## How to change thresholds safely

1. Run perf tests locally at least 3 times and record timings.
2. If CI is slower, run in CI perf job and compare p95 timings.
3. Update constants in `tests/perf/test_large_project_perf.py` only when sustained behavior requires it.
4. Keep query guard in place; increase only with a documented reason (schema/feature expansion).
