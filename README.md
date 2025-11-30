# Norrviq Måleri AB — сметы и финансы

Внутренняя двуязычная (RU/SV) система на FastAPI для расчёта смет, финансов и управления проектами компании Norrviq Måleri AB. Приложение использует SQLite, SQLAlchemy, Alembic и Jinja2-шаблоны с переключением языков.

## Installation & Run (local)

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/Dennicka/Norrviq.git
   cd Norrviq
   ```
2. Создайте виртуальное окружение и активируйте его:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
3. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```
4. Примените миграции базы данных:
   ```bash
   alembic upgrade head
   ```
5. Установите переменные окружения для доступа:
   ```bash
   export ADMIN_USERNAME=admin
   export ADMIN_PASSWORD=admin
   export SECRET_KEY="your-secret-key"
   ```
6. Запустите сервер разработки:
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
   ```
7. Откройте http://127.0.0.1:8001 и переключайте язык через ссылки RU/SV в верхнем меню.

## Login

По умолчанию используется пара admin/admin. Сразу смените эти значения через переменные окружения, чтобы избежать рисков для безопасности.
