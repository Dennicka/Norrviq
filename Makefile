.PHONY: check lint test migrate run preflight doctor bootstrap bootstrap-local run-local i18n-audit test-acceptance acceptance release-check reset-db alembic-check pdf-install

check: lint test alembic-check

lint:
	ruff check .

test:
	pytest -q

migrate:
	alembic upgrade head

run:
	uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

preflight:
	bash scripts/ops/preflight.sh

doctor:
	python -m app.scripts.doctor

pdf-install:
	python -m playwright install chromium

alembic-check:
	python -m alembic heads | tee /tmp/alembic-heads.txt
	@test "$$(grep -c '(head)' /tmp/alembic-heads.txt)" -eq 1

bootstrap:
	@if [ ! -d .venv ]; then python3 -m venv .venv; fi
	. .venv/bin/activate; pip install --upgrade pip; pip install -r requirements.txt
	@if [ ! -f .env ]; then cp .env.example .env; fi
	. .venv/bin/activate; alembic upgrade head
	. .venv/bin/activate; python -m app.scripts.create_admin || true

reset-db:
	rm -f norrviq.db ci.sqlite3 ci-perf.sqlite3

i18n-audit:
	bash scripts/i18n_audit.sh

bootstrap-local:
	bash scripts/ops/bootstrap_local.sh

run-local:
	APP_ENV=local COOKIE_SECURE=false uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

test-acceptance:
	pytest -q tests/e2e/test_acceptance_estimator_correctness.py

acceptance:
	pytest -q -m acceptance

release-check:
	python scripts/release_check.py
