#!/usr/bin/env python3
"""Seed development data. This script inserts data only and does not create schema."""

from app.db import SessionLocal
from app.models.settings import get_or_create_settings
from app.services.auth import ensure_admin_user
from app.services.bootstrap import (
    ensure_default_cost_categories,
    ensure_default_legal_notes,
    ensure_default_worktypes,
)


def main() -> None:
    db = SessionLocal()
    try:
        get_or_create_settings(db)
        ensure_default_cost_categories(db)
        ensure_default_legal_notes(db)
        ensure_default_worktypes(db)
        ensure_admin_user(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
