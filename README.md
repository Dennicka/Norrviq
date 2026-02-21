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

## Run locally

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Откройте http://127.0.0.1:8001 и переключайте язык через ссылки RU/SV в верхнем меню.

## Admin bootstrap

При старте приложение создаёт admin-пользователя из `ADMIN_EMAIL`/`ADMIN_PASSWORD`, если такого пользователя ещё нет.
Если admin уже существует, запись не изменяется.

## How to run tests

```bash
ruff check .
pytest
```
