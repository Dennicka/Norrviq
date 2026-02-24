#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "[bootstrap-local] created .env from .env.example"
fi

python - <<'PY'
import secrets
from pathlib import Path

env_path = Path('.env')
lines = env_path.read_text().splitlines() if env_path.exists() else []
vals = {}
for ln in lines:
    if '=' in ln and not ln.strip().startswith('#'):
        k,v=ln.split('=',1)
        vals[k]=v

def set_default(k,v):
    if not vals.get(k):
        vals[k]=v

set_default('APP_ENV','local')
set_default('COOKIE_SECURE','false')
set_default('DATABASE_URL','sqlite:///./norrviq.db')
if len(vals.get('SESSION_SECRET','')) < 32:
    vals['SESSION_SECRET']=secrets.token_urlsafe(48)

ordered=[]
seen=set()
for ln in lines:
    if '=' in ln and not ln.strip().startswith('#'):
        k=ln.split('=',1)[0]
        ordered.append(f"{k}={vals[k]}")
        seen.add(k)
    else:
        ordered.append(ln)
for k,v in vals.items():
    if k not in seen:
        ordered.append(f"{k}={v}")

env_path.write_text("\n".join(ordered)+"\n")
print('[bootstrap-local] ensured APP_ENV, COOKIE_SECURE, DATABASE_URL, SESSION_SECRET')
PY
