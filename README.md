# Norrviq Måleri AB Estimator

A bilingual (Russian/Swedish) FastAPI skeleton for Norrviq Måleri AB's future estimating and finance system. The project includes a minimal FastAPI backend with SQLite, SQLAlchemy, Alembic migrations, and Jinja2 templates for a starter web UI.

## Getting started

1. Create and activate a virtual environment (example using `python -m venv .venv`).
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the development server:

   ```bash
   uvicorn app.main:app --reload
   ```

4. Open the app at http://127.0.0.1:8000 and switch languages via the RU/SV links in the top navigation.
