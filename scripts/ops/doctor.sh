#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "[doctor] repo: $ROOT_DIR"
python - <<'PY'
import os, pathlib, sys
from urllib.parse import urlparse

errors=[]
warn=[]
py=sys.version_info
print(f"[doctor] python={py.major}.{py.minor}.{py.micro}")
if py < (3,11):
    errors.append("Python 3.11+ required")

venv=os.getenv('VIRTUAL_ENV')
if not venv:
    warn.append("virtualenv not active. Run: python3.11 -m venv .venv && source .venv/bin/activate")
else:
    print(f"[doctor] venv={venv}")

if not pathlib.Path('.env').exists():
    errors.append('.env missing. Run: make bootstrap-local')

req_ok=pathlib.Path('requirements.txt').exists()
print(f"[doctor] requirements.txt={'ok' if req_ok else 'missing'}")

secret=os.getenv('SESSION_SECRET','')
if len(secret) < 32:
    warn.append('SESSION_SECRET length < 32 in current shell env; ensure .env is loaded')

db_url=os.getenv('DATABASE_URL','sqlite:///./norrviq.db')
parsed=urlparse(db_url)
if parsed.scheme.startswith('sqlite'):
    db_path = pathlib.Path((parsed.path or './norrviq.db').lstrip('/')).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not os.access(db_path.parent, os.W_OK):
        errors.append(f'DB directory not writable: {db_path.parent}')
    else:
        print(f"[doctor] db_path={db_path}")

if warn:
    print('[doctor] warnings:')
    [print(f'  - {w}') for w in warn]
if errors:
    print('[doctor] errors:')
    [print(f'  - {e}') for e in errors]
    print('[doctor] next: make bootstrap-local && make migrate && make run-local')
    raise SystemExit(1)
print('[doctor] next: make migrate && make run-local')
PY
