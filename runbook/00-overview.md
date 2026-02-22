# Production runbook — overview

Этот runbook описывает эксплуатацию сервиса Estimator/Norrviq в production: развертывание, конфиг, миграции, backup/restore, обновления, диагностику и release-checklist.

## Что это за сервис

- Backend: FastAPI (`app.main:app`).
- ORM/DB: SQLAlchemy + SQLite.
- Миграции схемы: только Alembic.
- Веб-интерфейс: серверные HTML-шаблоны (Jinja2).
- Ключевые operational endpoints:
  - `GET /healthz` — liveness.
  - `GET /readyz` — readiness (DB + Alembic head).
  - `GET /metrics/basic` — базовые метрики.

## Runtime dependencies

- Python **3.11**.
- Linux-пакеты для PDF рендера (WeasyPrint):
  - `libcairo2`, `libpango-1.0-0`, `libpangoft2-1.0-0`, `libgdk-pixbuf-2.0-0`, `libffi8`, `shared-mime-info`, `fonts-dejavu`.
- SQLite DB файл:
  - путь задаётся через `DATABASE_URL` (например `sqlite:////srv/norrviq/data/norrviq.db`).
- Папка бэкапов:
  - `BACKUP_DIR` (например `/srv/norrviq/backups`).

## Где хранятся конфиги, логи, данные

Рекомендуемый layout на VPS:

```text
/srv/norrviq/
  app/                  # git checkout
  .venv/                # production virtualenv
  shared/.env           # production env (секреты не в git)
  data/norrviq.db       # sqlite
  backups/              # backup .db + .sha256
  logs/                 # app logs (если не journalctl)
```

- Конфиг приложения: env-переменные (см. `runbook/01-config.md`).
- Логи:
  - рекомендуется `LOG_FORMAT=json` в prod;
  - для systemd: смотреть через `journalctl -u <service>`.
- Alembic конфиг: `alembic.ini` в корне репозитория.

## Runbook map

1. `runbook/01-config.md` — ENV и секреты.
2. `runbook/02-deploy.md` — deploy на VPS.
3. `runbook/03-migrations.md` — миграции.
4. `runbook/04-backup-restore.md` — backup/restore.
5. `runbook/05-upgrade.md` — безопасный upgrade/rollback.
6. `runbook/06-troubleshooting.md` — troubleshooting.
7. `runbook/07-security.md` — security операции.
8. `runbook/08-release-checklist.md` — pre/post release checklist.
