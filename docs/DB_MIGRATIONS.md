# DB migrations policy

## Single source of truth

Schema management is **Alembic-only**. Do not use `Base.metadata.create_all()` in runtime code or tests.

## Common commands

- Upgrade to latest revision:
  ```bash
  python scripts/db_upgrade.py
  ```
- Show current revision:
  ```bash
  python scripts/db_current.py
  ```
- Downgrade one revision (dev only):
  ```bash
  python scripts/db_downgrade.py
  ```

## Naming and revision rules

- Create migrations with meaningful messages, for example:
  ```bash
  alembic revision -m "add_invoices_due_date"
  ```
- Every revision should have both `upgrade()` and `downgrade()`.
- Keep operations deterministic and idempotent where possible.
- Data seed belongs in seed scripts, never in schema creation flow.

## Troubleshooting

If app startup says schema is out of date, run:

```bash
python scripts/db_upgrade.py
```

Then restart the app.
