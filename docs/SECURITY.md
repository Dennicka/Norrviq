# Security model (v1)

## Secrets

- Секреты не хранятся в коде.
- Используются только переменные окружения: `APP_ENV`, `SESSION_SECRET`, `COOKIE_SECURE`, `COOKIE_SAME_SITE`.
- В non-local средах приложение не запускается без `SESSION_SECRET` (минимум 32 байта).

## Passwords

- Пароли пользователей хранятся только как `password_hash`.
- Используется адаптивное `scrypt`-хеширование с солью и проверка через `verify_password`.
- Default credentials удалены; первый admin создаётся только через CLI `python -m app.scripts.create_admin`.

## Sessions / Cookies

- Cookie настроены с `HttpOnly=true`, `SameSite=Lax`.
- `Secure` управляется `COOKIE_SECURE` (обычно `true` в prod/HTTPS).
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

## CSRF

- Применяется защита для всех state-changing методов: `POST`, `PUT`, `PATCH`, `DELETE`.
- Источник истины токена — серверная сессия (`session["csrf_token"]`).
- Токен создаётся при первом безопасном запросе и затем переиспользуется в рамках сессии.
- Валидация токена:
  - HTML forms: hidden input `csrf_token`.
  - JS/XHR/fetch: header `X-CSRF-Token`.
- Исключения строго ограничены: `GET/HEAD/OPTIONS`, `/api/health`, `/static/*`.
- Ошибка валидации возвращает `HTTP 403` с сообщением `Invalid or missing CSRF token`.
- События отклонения логируются как `csrf_reject` с `path`, `method`, `user_id`, `request_id`.
