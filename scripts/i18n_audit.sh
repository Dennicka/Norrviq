#!/usr/bin/env bash
set -euo pipefail

# Lightweight check for likely hardcoded user-facing strings.
# Excludes migrations/tests/static vendor-like files.

fail=0

check_pattern() {
  local pattern="$1"
  local label="$2"
  local results
  results=$(rg -n "$pattern" app/templates app/routers app/services \
    -g '!**/migrations/**' -g '!**/alembic/**' -g '!**/tests/**' -g '!**/static/**' || true)
  if [[ -n "$results" ]]; then
    echo "[i18n-audit] potential $label strings:"
    echo "$results"
    fail=1
  fi
}

check_pattern '>[[:space:]]*[A-Za-zА-Яа-я][^<{]*<' 'template literal'
check_pattern 'add_flash_message\([^\n]*"[A-Za-zА-Яа-я]' 'flash literal'
check_pattern 'HTTPException\([^\n]*detail="[A-Za-zА-Яа-я]' 'HTTPException literal'

if [[ "$fail" -eq 1 ]]; then
  echo "[i18n-audit] FAILED"
  exit 1
fi

echo "[i18n-audit] OK"
