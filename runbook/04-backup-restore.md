# Runbook — backup & restore

## Backup

### Через UI

1. Зайти под `admin` в `/admin/backups`.
2. Нажать **Create backup**.
3. Файл будет сохранён в `BACKUP_DIR` как `backup_YYYYMMDD_HHMMSS_micro.db`.
4. Рядом создаётся `<filename>.sha256`.

### Проверка checksum (CLI)

```bash
cd /srv/norrviq/backups
sha256sum -c backup_20260101_120000_000001.db.sha256
```

Ожидается `OK`.

## Restore

### Через UI (поддерживаемый путь)

1. Открыть `/admin/backups`.
2. В секции restore загрузить `.db` (и опционально `.sha256`).
3. Ввести confirmation word: `RESTORE`.
4. Система автоматически:
   - проверяет SQLite header;
   - делает `PRAGMA integrity_check`;
   - проверяет совместимость Alembic head;
   - переводит сервис в maintenance mode на время swap;
   - создаёт `pre_restore_backup_*.db`;
   - выполняет `alembic upgrade head`.

## Recovery scenarios

### Сценарий A — неудачный deploy

1. Остановить трафик (maintenance window/reverse proxy drain).
2. Сделать restore из последнего валидного backup через UI.
3. Проверить:

```bash
curl -fsS http://127.0.0.1:8001/readyz
curl -fsS http://127.0.0.1:8001/healthz
```

### Сценарий B — повреждение БД

1. Остановить сервис.
2. Скопировать текущий `norrviq.db` для форензики.
3. Запустить сервис и выполнить restore в UI из последнего корректного backup.
4. Проверить ключевые user-flows (invoice/offer/pdf).

## Рекомендации

- Делать backup **перед** deploy/миграциями.
- Хранить off-host копию.
- Периодически запускать checksum verification.
