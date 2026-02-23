# Runbook — configuration

## ENV переменные

Ниже перечислены runtime-переменные из `app.config.Settings`.

### Обязательные для production

- `APP_ENV=prod`
- `SESSION_SECRET=<secret>`
  - минимум 32 байта (raw string / hex / base64).
- `DATABASE_URL=sqlite:////srv/norrviq/data/norrviq.db`
- `COOKIE_SECURE=true`

### Рекомендуемые для production

- `COOKIE_SAME_SITE=lax`
- `LOG_FORMAT=json`
- `LOG_LEVEL=INFO`
- `BACKUP_DIR=/srv/norrviq/backups`
- `BACKUP_RETENTION_DAYS=30`
- `BACKUP_MAX_FILES=50`
- `SESSION_COOKIE_NAME=norrviq_session`
- `SESSION_MAX_AGE_SECONDS=604800`

### Только для local/dev

- `ADMIN_BOOTSTRAP_ENABLED` (в prod держать `false`).
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` (bootstrap-only).
- `ALLOW_DEV_DEFAULTS` (legacy; не использовать для prod).


## Минимальный `.env` для local

```env
APP_ENV=local
DATABASE_URL=sqlite:///./norrviq.db
BACKUP_DIR=./backups
```

`SESSION_SECRET` в local необязателен, но в non-local обязателен и валидируется на длину.

## Пример `.env` для production

```env
APP_ENV=prod
SESSION_SECRET=replace_with_32plus_bytes_secret
DATABASE_URL=sqlite:////srv/norrviq/data/norrviq.db

COOKIE_SECURE=true
COOKIE_SAME_SITE=lax
SESSION_COOKIE_NAME=norrviq_session
SESSION_MAX_AGE_SECONDS=604800

LOG_FORMAT=json
LOG_LEVEL=INFO

BACKUP_DIR=/srv/norrviq/backups
BACKUP_RETENTION_DAYS=30
BACKUP_MAX_FILES=50

ADMIN_BOOTSTRAP_ENABLED=false
```

## Требования к `SESSION_SECRET`

Проверка в приложении:

- для `APP_ENV != local` отсутствие секрета приводит к startup error;
- длина декодированного секрета должна быть минимум 32 байта.

Генерация секрета:

```bash
python - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

## Где хранить секреты

- Не хранить в git.
- Рекомендуется:
  - `EnvironmentFile=/srv/norrviq/shared/.env` (systemd) с `chmod 600`;
  - либо внешний secret manager (1Password/Bitwarden/Vault/SOPS).
- Ротация секрета: см. `runbook/07-security.md`.
