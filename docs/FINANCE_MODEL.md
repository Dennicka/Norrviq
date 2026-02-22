# Finance Model

## Estimated hours vs worker assignment hours

- **Estimated hours** (`estimated_hours_raw`) come from estimator scope: sum of `project_work_items.calculated_hours`.
- Speed profile is applied on top of estimate:
  - `estimated_hours = estimated_hours_raw * speed_multiplier` (quantized to 0.01h).
- **Worker assignments hours** (`planned_hours` / `actual_hours`) are used for payroll and execution tracking, not as estimator baseline.

This split prevents baseline from collapsing to zero when workers are not assigned yet.

## Internal labor hourly rate

Single source for pricing baseline:

1. If assignments are present with positive hours and hourly rates:
   - use weighted average by assignment hours
   - `internal_hourly_rate = sum(hours * rate) / sum(hours)`
   - assignments with `hours <= 0` are ignored.
2. If no usable assignments exist:
   - fallback to `settings.default_worker_hourly_rate`.

## Internal labor cost formula

- `salary_fund = estimated_hours * internal_hourly_rate`
- `labor_cost_internal = salary_fund * (1 + employer_contributions_percent / 100)`
- Money values are quantized to `0.01`.

Invariant enforced by model:

- if `estimated_hours > 0` and `internal_hourly_rate > 0`, then `labor_cost_internal > 0`.

## Why this matters for floor policy

Floor, profit, margin, and conversions depend on `internal_total_cost`. If labor cost is incorrectly zero, floor checks are too permissive and margin is overstated. Using estimate-based labor hours with a deterministic internal rate keeps floor decisions realistic even before worker assignment.
