.PHONY: check migrate run preflight doctor i18n-audit

check:
	ruff check .
	pytest -q

migrate:
	alembic upgrade head

run:
	uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

preflight:
	bash scripts/ops/preflight.sh

doctor:
	bash scripts/ops/doctor.sh

i18n-audit:
	bash scripts/i18n_audit.sh
