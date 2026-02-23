from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import Request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger("uvicorn.error")


class FormValidationError(ValueError):
    """Raised when form field parsing fails."""


def clean_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def parse_checkbox(value: Any) -> bool:
    if value is None:
        return False
    normalized = str(value).strip().lower()
    return normalized in {"1", "true", "on", "yes"}


def parse_int_field(value: Any, *, field_name: str, required: bool = False, min_value: int | None = None, max_value: int | None = None) -> int | None:
    normalized = clean_str(value)
    if normalized is None:
        if required:
            raise FormValidationError(f"{field_name} is required")
        return None
    try:
        parsed = int(normalized)
    except (TypeError, ValueError) as exc:
        raise FormValidationError(f"{field_name} must be an integer") from exc
    if min_value is not None and parsed < min_value:
        raise FormValidationError(f"{field_name} must be >= {min_value}")
    if max_value is not None and parsed > max_value:
        raise FormValidationError(f"{field_name} must be <= {max_value}")
    return parsed


def parse_decimal_field(value: Any, *, field_name: str, required: bool = False, min_value: Decimal | None = None) -> Decimal | None:
    normalized = clean_str(value)
    if normalized is None:
        if required:
            raise FormValidationError(f"{field_name} is required")
        return None
    try:
        parsed = Decimal(normalized)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FormValidationError(f"{field_name} must be a number") from exc
    if min_value is not None and parsed < min_value:
        raise FormValidationError(f"{field_name} must be >= {min_value}")
    return parsed


def safe_commit(db: Session, request: Request, *, message: str) -> bool:
    request_id = getattr(request.state, "request_id", "unknown")
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        logger.exception("db_integrity_error request_id=%s message=%s", request_id, message)
        return False
    except SQLAlchemyError:
        db.rollback()
        logger.exception("db_sqlalchemy_error request_id=%s message=%s", request_id, message)
        return False
