# Estimator — сметы и финансы

Внутренняя двуязычная (RU/SV) система на FastAPI для расчёта смет, финансов и управления проектами. Приложение использует SQLite, SQLAlchemy, Alembic и Jinja2-шаблоны с переключением языков.

## Python version

- Рекомендуемая версия: **Python 3.11**

## Installation

1. Клонируйте репозиторий:
   ```bash
   git clone <your-repo-url>
   cd <your-repo-dir>
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

## Company profile (Trenor Måleri AB)

После первого запуска откройте `Settings → Company` (`/settings/company`) и заполните реквизиты:
- `legal_name`: `Trenor Måleri AB`
- `org_number`, `vat_number`
- адрес и контакты
- минимум один платёжный метод (`bankgiro` / `plusgiro` / `iban`)
- `payment_terms_days`, `invoice_prefix`, `offer_prefix`

Эти данные автоматически используются в Offert/Faktura шаблонах.


## Offer/Invoice numbering and finalize flow

- Draft documents are created without official number.
- Number is assigned only on **Finalize/Issue** actions (`POST /offers/{id}/finalize`, `POST /invoices/{id}/finalize`).
- Status lifecycle: `draft -> issued`.
- Format: `<prefix><year>-<seq>` where `seq` uses left-zero padding from `company_profile.document_number_padding` (default `4`).
- Sequences are stored in DB table `document_sequences` (separate for `offer` and `invoice`, unique by type+year).
- Finalize is idempotent: repeated finalize returns the same number and does not consume a new one.


## Pricing screen

- Экран настройки ценообразования проекта: `/projects/{id}/pricing`.
- Описание режимов и полей: `docs/PRICING.md`.

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

## How to run tests

```bash
ruff check .
pytest
```

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

Для встроенного UI также доступен helper `window.appFetch(url, options)`, который автоматически добавляет `X-CSRF-Token`.
