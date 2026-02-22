# Backup & Restore (SQLite)

## Backup

- Open `/admin/backups` as admin.
- Click **Create backup**.
- Backup files are saved in `BACKUP_DIR` (default `./backups`).
- Filenames use `backup_YYYYMMDD_HHMMSS.db`.
- A checksum sidecar `<filename>.sha256` is created.

## Download & Verify

- Admin and auditor can download backups.
- Use **Verify checksum** to compare current file hash with metadata.

## Restore

- Admin-only.
- Upload `.db` in **Restore database** section.
- Type exact confirmation word `RESTORE`.
- The workflow validates:
  - SQLite file header (`SQLite format 3`)
  - `PRAGMA integrity_check` must return `ok`
  - Alembic head compatibility
- Before swap, current DB is copied to `pre_restore_backup_YYYYMMDD_HHMMSS.db`.
- Service enters maintenance mode while restore/swap runs.
- Then `alembic upgrade head` is executed.

## Retention policy

Controlled by env vars:

- `BACKUP_RETENTION_DAYS` (default `30`)
- `BACKUP_MAX_FILES` (default `50`)

After each successful backup, old backups are pruned by those limits.

## Best practices

- Always create a backup before major schema/data changes.
- Store a copy outside app host as well.
- Periodically verify checksums.
