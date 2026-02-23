#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "[doctor] repo: $ROOT_DIR"

if ! command -v python >/dev/null 2>&1; then
  echo "[doctor] python is required" >&2
  exit 1
fi

if ! command -v alembic >/dev/null 2>&1; then
  echo "[doctor] alembic is required" >&2
  exit 1
fi

python - <<'PY'
import os
import pathlib
import sys
from urllib.parse import urlparse

errors = []
py = sys.version_info
if py < (3, 10):
    errors.append(f"Python 3.10+ required, found {py.major}.{py.minor}.{py.micro}")
else:
    print(f"[doctor] python={py.major}.{py.minor}.{py.micro}")

env_path = pathlib.Path('.env')
if not env_path.exists():
    errors.append("Missing .env file (minimum local config: APP_ENV=local, DATABASE_URL=sqlite:///./norrviq.db)")
else:
    print(f"[doctor] .env={env_path.resolve()}")

database_url = os.getenv('DATABASE_URL', 'sqlite:///./norrviq.db')
parsed = urlparse(database_url)
if not parsed.scheme:
    errors.append(f"DATABASE_URL is not parseable: {database_url}")
else:
    print(f"[doctor] database_scheme={parsed.scheme}")

backup_dir = pathlib.Path(os.getenv('BACKUP_DIR', './backups')).resolve()
backup_dir.mkdir(parents=True, exist_ok=True)
if not os.access(backup_dir, os.R_OK | os.W_OK | os.X_OK):
    errors.append(f"BACKUP_DIR is not writable: {backup_dir}")
else:
    print(f"[doctor] backup_dir={backup_dir}")

if errors:
    print("[doctor] issues found:", file=sys.stderr)
    for issue in errors:
        print(f"  - {issue}", file=sys.stderr)
    sys.exit(1)
PY

echo "[doctor] migration status"
alembic current
alembic heads

echo "[doctor] ok"
