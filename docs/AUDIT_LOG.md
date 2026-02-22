# Unified Audit Log

`audit_log` is the single immutable table for critical events.

## Logged actions
- auth: `login_success`, `login_failed`, `logout`
- document issuance/finalization (`offer_issued`, `invoice_issued`, quality/floor/completeness blocks)
- invoice line generation/recalculation
- settings and terms template changes

## Integrity chain
Each row stores `prev_hash` and `hash`.

`hash = sha256(prev_hash + canonical_json(record_fields))`

Run:

```bash
python scripts/verify_audit_chain.py
```

## Request correlation
Every audit entry includes `request_id` when available from middleware.
Use `/admin/audit` filters or exports to find all records by `request_id`.

## Security rules
- No passwords/secrets/CSRF tokens in `metadata_json`.
- Audit records are append-only (update/delete is blocked by model events).
