.PHONY: check migrate run preflight i18n-audit

check:
	ruff check .
	pytest -q

migrate:
	alembic upgrade head

run:
	uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

preflight:
	bash scripts/ops/preflight.sh


i18n-audit:
	bash scripts/i18n_audit.sh
