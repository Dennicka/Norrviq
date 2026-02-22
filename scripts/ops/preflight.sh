#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "[preflight] repo: $ROOT_DIR"

for cmd in python alembic; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[preflight] missing command: $cmd" >&2
    exit 1
  fi
done

python - <<'PY'
import base64
import os
import pathlib
import sys


def decode_secret(value: str) -> bytes:
    try:
        return bytes.fromhex(value)
    except ValueError:
        pass
    try:
        return base64.b64decode(value, validate=True)
    except Exception:
        return value.encode("utf-8")

app_env = os.getenv("APP_ENV", "local")
secret = os.getenv("SESSION_SECRET", "")
database_url = os.getenv("DATABASE_URL", "sqlite:///./norrviq.db")
backup_dir = os.getenv("BACKUP_DIR", "./backups")

if app_env != "local":
    if not secret:
        print("[preflight] SESSION_SECRET is required when APP_ENV != local", file=sys.stderr)
        sys.exit(1)
    if len(decode_secret(secret)) < 32:
        print("[preflight] SESSION_SECRET must be >= 32 bytes (raw/hex/base64)", file=sys.stderr)
        sys.exit(1)

if not database_url.startswith("sqlite:///"):
    print("[preflight] only sqlite DATABASE_URL is supported in current ops scripts", file=sys.stderr)
    sys.exit(1)

db_path = pathlib.Path(database_url.replace("sqlite:///", "", 1)).resolve()
db_path.parent.mkdir(parents=True, exist_ok=True)
backup_path = pathlib.Path(backup_dir).resolve()
backup_path.mkdir(parents=True, exist_ok=True)

for p in (db_path.parent, backup_path):
    if not os.access(p, os.R_OK | os.W_OK | os.X_OK):
        print(f"[preflight] insufficient permissions on {p}", file=sys.stderr)
        sys.exit(1)

print(f"[preflight] APP_ENV={app_env}")
print(f"[preflight] DATABASE_URL={database_url}")
print(f"[preflight] DB_DIR={db_path.parent}")
print(f"[preflight] BACKUP_DIR={backup_path}")
PY

echo "[preflight] alembic current"
alembic current

echo "[preflight] alembic heads"
alembic heads

echo "[preflight] ok"
