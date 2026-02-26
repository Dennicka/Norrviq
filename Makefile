.PHONY: check migrate run preflight doctor bootstrap-local run-local i18n-audit test-acceptance

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

bootstrap-local:
	bash scripts/ops/bootstrap_local.sh

run-local:
	APP_ENV=local COOKIE_SECURE=false uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

test-acceptance:
	pytest -q tests/e2e/test_acceptance_estimator_correctness.py
