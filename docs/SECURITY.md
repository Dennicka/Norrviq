# Security model (v1)

## Secrets

- Секреты не хранятся в коде.
- Используются только переменные окружения: `APP_SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ALLOW_DEV_DEFAULTS`.
- В production (`ALLOW_DEV_DEFAULTS=false`) приложение не запускается без `APP_SECRET_KEY`.

## Passwords

- Пароли пользователей хранятся только как `password_hash`.
- Используется scrypt-хеширование с солью и проверка через verify.
- Bootstrap admin создаётся из env только при отсутствии пользователя.

## Sessions / Cookies

- Cookie настроены с `HttpOnly=true`, `SameSite=Lax`.
- `Secure=true` при `ALLOW_DEV_DEFAULTS=false`, для local dev может быть `false`.
- При login выполняется ротация сессии (новый `sid`).
- Logout очищает сессию.

## Roles (RBAC)

- Базовые роли: `admin`, `operator`, `viewer`.
- Доступ к `/settings` ограничен ролью `admin`.
- Добавлена зависимость `require_role(...)` для расширения защиты на другие роуты.

## Auth audit events

Логируются события:
- `login_success`
- `login_failed`
- `logout`
- `admin_created`

Логи не содержат пароли и секреты.
