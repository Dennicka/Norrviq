# Norrviq Måleri AB — сметы и финансы

Внутренняя двуязычная (RU/SV) система на FastAPI для расчёта смет, финансов и управления проектами компании Norrviq Måleri AB. Приложение использует SQLite, SQLAlchemy, Alembic и Jinja2-шаблоны с переключением языков.

## Python version

- Рекомендуемая версия: **Python 3.11**

## Installation

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/Dennicka/Norrviq.git
   cd Norrviq
   ```
2. Создайте виртуальное окружение и активируйте его:
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   ```
3. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```
4. Скопируйте пример окружения и заполните переменные:
   ```bash
   cp .env.example .env
   ```
5. Примените миграции базы данных:
   ```bash
   alembic upgrade head
   ```

## Environment variables

- `APP_SECRET_KEY` — обязательный секрет для сессий в production (`ALLOW_DEV_DEFAULTS=false`), минимум 32 байта (raw/hex/base64).
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` — учётные данные для bootstrap admin-пользователя при первом запуске (idempotent).
- `ALLOW_DEV_DEFAULTS` — только для локальной разработки; по умолчанию `false`.
- `LOG_FORMAT` — формат логов: `pretty` (dev) или `json` (production).
- `LOG_LEVEL` — уровень логирования (`INFO`, `WARN`, `ERROR`).

## Database initialization and migrations

Schema is managed only by Alembic.

- Initialize/upgrade DB to latest schema:
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
- Seed development data (data only, no schema creation):
  ```bash
  python scripts/seed_dev.py
  ```

If you see a startup error about outdated DB, run `python scripts/db_upgrade.py` (or `alembic upgrade head`) and restart.

Detailed policy: `docs/DB_MIGRATIONS.md`.

## Run locally

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Откройте http://127.0.0.1:8001 и переключайте язык через ссылки RU/SV в верхнем меню.

## Admin bootstrap

При старте приложение создаёт admin-пользователя из `ADMIN_EMAIL`/`ADMIN_PASSWORD`, если такого пользователя ещё нет.
Если admin уже существует, запись не изменяется.


## Observability endpoints

- `GET /healthz` — liveness (процесс жив).
- `GET /readyz` — readiness (проверка подключения к БД и актуальности миграций Alembic).
- `GET /metrics/basic` — базовые метрики (`request_latency_seconds`, `request_count_total`, `errors_total`).

Подробности: `docs/OBSERVABILITY.md`.

## How to run tests

```bash
ruff check .
pytest
```

## CSRF protection: how it works

- Все state-changing запросы (`POST`, `PUT`, `PATCH`, `DELETE`) требуют CSRF-токен.
- Токен хранится в сессии (`session["csrf_token"]`) и автоматически создаётся на первом безопасном запросе (`GET/HEAD/OPTIONS`).
- Для HTML-форм токен передаётся через скрытое поле `csrf_token` (через шаблонный helper `csrf_input(request)`).
- Для JS/fetch токен публикуется в `<meta name="csrf-token">` и должен отправляться в заголовке `X-CSRF-Token`.
- Исключения: только `GET/HEAD/OPTIONS`, `/api/health`, `/static/*`.
- При отсутствии/невалидности токена сервер возвращает `403 Invalid or missing CSRF token`.

## How to send token from JS

```html
<meta name="csrf-token" content="{{ csrf_token }}">
```

```js
const token = document.querySelector('meta[name="csrf-token"]').content;
await fetch('/clients/new', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
    'X-CSRF-Token': token,
  },
  body: new URLSearchParams({ name: 'Demo Client', csrf_token: token }),
});
```

Для встроенного UI также доступен helper `window.norrviqFetch(url, options)`, который автоматически добавляет `X-CSRF-Token`.
