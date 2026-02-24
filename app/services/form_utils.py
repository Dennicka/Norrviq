from __future__ import annotations

from decimal import Decimal, InvalidOperation


def get_str(form, key: str, default: str = "") -> str:
    value = form.get(key)
    return str(value).strip() if value is not None else default


def get_bool(form, key: str, default: bool = False) -> bool:
    value = str(form.get(key) or "").strip().lower()
    if value in {"1", "true", "on", "yes"}:
        return True
    if value in {"0", "false", "off", "no"}:
        return False
    return default


def get_int(form, key: str, default: int = 0) -> int:
    raw = str(form.get(key) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_decimal(form, key: str, default: Decimal = Decimal("0")) -> Decimal:
    raw = str(form.get(key) or "").strip().replace(",", ".")
    if not raw:
        return default
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return default
