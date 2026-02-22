#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

REF="${1:-}"
SERVICE_NAME="${SERVICE_NAME:-norrviq}"
RESTART_CMD="${RESTART_CMD:-systemctl restart ${SERVICE_NAME}}"

if [[ -n "$REF" ]]; then
  echo "[upgrade] checking out ref: $REF"
  git fetch --tags --prune
  git checkout "$REF"
fi

echo "[upgrade] running preflight"
"$ROOT_DIR/scripts/ops/preflight.sh"

echo "[upgrade] installing deps"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "[upgrade] running migrations"
alembic upgrade head

if command -v systemctl >/dev/null 2>&1; then
  echo "[upgrade] restarting service via: $RESTART_CMD"
  sudo bash -lc "$RESTART_CMD"
else
  echo "[upgrade] systemctl not found; restart service manually" >&2
fi

echo "[upgrade] done"
