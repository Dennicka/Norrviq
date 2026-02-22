.PHONY: check

check:
	ruff check .
	pytest -q
