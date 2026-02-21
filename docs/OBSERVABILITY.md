# Observability

## Endpoints

- `GET /healthz` — liveness probe (`200 {"status":"ok"}`), only process health.
- `GET /readyz` — readiness probe (DB connectivity + Alembic head check). Returns `503` with `reason` when unavailable.
- `GET /metrics/basic` — basic metrics payload for scraping/inspection.

## Request ID workflow

- Every request receives `X-Request-Id`.
- If inbound header `X-Request-Id` exists, it is propagated as-is.
- On incidents: copy `request_id` from response/UI error page and search in logs.

## Logging

- `LOG_FORMAT=json` for production (structured logs).
- `LOG_FORMAT=pretty` for local debugging.
- `LOG_LEVEL` controls verbosity (`INFO`, `WARN`, `ERROR`).
- Access logs include: method, route template, status, latency, request_id, optional user_id.
- Secrets (passwords, CSRF tokens, secret keys) must not be logged.

## Metrics to watch

- `request_latency_seconds` (bucketed histogram counters) — watch p95/p99 trend.
- `request_count_total{method,path_template,status}` — request volume and error ratio.
- `errors_total` — count of `5xx` responses.

## Cardinality rule

Metrics and access logs use route templates (for example `/projects/{project_id}`), not raw URLs with dynamic IDs.
