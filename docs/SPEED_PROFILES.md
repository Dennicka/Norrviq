# Speed Profiles

Speed profiles apply a **Decimal multiplier** to labor hours.

- `SLOW = 1.20`
- `MEDIUM = 1.00` (default)
- `FAST = 0.85`

## How it works

1. Compute raw labor hours as before.
2. Apply speed: `labor_hours_after_speed = raw_labor_hours_total * multiplier`.
3. Compute buffers from `labor_hours_after_speed`.

Pricing breakdown exposes:
- `speed_profile_code`
- `speed_multiplier`
- `speed_hours_delta`

## Where to configure

- Admin CRUD: `/settings/speed-profiles`
- Employee default profile: `/workers/{id}/edit`
- Project profile override: `/projects/{id}/buffers`

Project-level choice is used for baseline/pricing in v1.

## Practical usage

- Use **FAST** for senior crews with stable process.
- Use **SLOW** for onboarding/new team members or constrained access.
- Keep **MEDIUM** if no strong signal.
