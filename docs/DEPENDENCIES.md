# Dependency pinning policy

This project uses **pinned versions** in `requirements.txt` to guarantee reproducible installs in local development and CI.

## Why pinned dependencies

- Predictable behavior: same resolver outcome across machines.
- Security and auditability: dependency set is explicit and reviewable.
- Stable CI: avoids random breakages from upstream minor/patch releases.
- Safer upgrades: dependency changes become intentional and visible in pull requests.

## How to update dependencies

1. Update version pins in `requirements.txt` intentionally (package-by-package).
2. Run quality gates locally:
   - `ruff check .`
   - `pytest`
3. Review release notes for FastAPI/Starlette/Uvicorn and DB stack packages.
4. Merge only when tests pass and behavior is validated.

## Critical runtime checks

At app startup, logs include import paths for `python-multipart` and `itsdangerous`.
This makes it obvious from logs that imports resolve from installed packages, not local shadow directories.
