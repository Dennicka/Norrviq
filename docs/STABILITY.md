# Stability gate

## Failure classes hardened

- Request parsing is standardized for form posts to avoid body stream double-consumption (`Stream consumed`) in core auth/worktypes handlers.
- Core write paths now use guarded DB commits with rollback + request-id logging for integrity and generic SQLAlchemy failures.
- Form parsing helpers centralize trimming, checkbox parsing, and integer/decimal validation to reduce copy-paste parsing bugs.
- Route ordering checks ensure static routes are declared before dynamic identifiers for core modules.

## Local smoke flow

Run:

```bash
pytest -q tests/e2e/test_smoke_flow.py
```

The scenario verifies: login, client/project creation, room add, pricing/takeoff/material pages, offer, invoice, and logout.

## Negative-path checks

Run:

```bash
pytest -q tests/test_auth.py tests/e2e/test_csrf_reject.py tests/test_route_ordering.py
```

Checks include invalid login, CSRF rejection without crashes, and static-vs-dynamic route declaration order.

## Post-merge checklist

1. Run `make doctor`.
2. Run `ruff check .`.
3. Run smoke and auth/csrf tests listed above.
4. Confirm logs include `request_id` for failed requests.

## Reading request_id in logs

- Every response includes `X-Request-Id`.
- Access and exception logs include `request_id`.
- Use request_id from UI/API response to correlate with server logs for root cause analysis.
