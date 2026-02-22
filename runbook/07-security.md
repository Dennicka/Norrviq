# Runbook — security operations

## RBAC роли

- `admin` — полный доступ, включая `/settings`, `/admin/backups`, `/admin/audit`.
- `auditor` — audit/backups read-only операции (download/verify).
- `operator` — рабочие операции в приложении.
- `viewer` — чтение/просмотр, включая PDF download.

## Ротация секретов

### `SESSION_SECRET`

1. Сгенерировать новый секрет.
2. Обновить `/srv/norrviq/shared/.env`.
3. Перезапустить сервис:

```bash
sudo systemctl restart norrviq
```

4. Проверить `readyz`.

> Важно: смена session secret инвалидирует текущие сессии пользователей.

## Создание / сброс admin

Создание первого admin (или дополнительного):

```bash
cd /srv/norrviq/app
source /srv/norrviq/.venv/bin/activate
python -m app.scripts.create_admin --email admin@example.com --password 'StrongPassword#2026'
```

Если нужен reset пароля существующего admin, выполнить через админ-функционал/DB-операцию по внутреннему регламенту (не хранить пароль в shell history).

## Audit log operations

- UI: `/admin/audit`
- CSV export: `/admin/audit/export.csv`
- Проверка целостности цепочки:

```bash
cd /srv/norrviq/app
source /srv/norrviq/.venv/bin/activate
python scripts/verify_audit_chain.py
```

Искать события:
- auth: `login_success`, `login_failed`, `logout`, `admin_created`;
- backups: `db_backup_created`, `db_backup_verified`, `db_backup_restored`;
- документы: `offer_issued`, `invoice_issued`, `*_pdf_downloaded`.
