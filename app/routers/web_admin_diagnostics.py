import os
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.company_profile import get_or_create_company_profile
from app.models.pricing_policy import get_or_create_pricing_policy

router = APIRouter(prefix="/admin/diagnostics", tags=["admin-diagnostics"])


@router.get("", response_class=HTMLResponse)
async def diagnostics_page(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    settings = get_settings()
    db_url = settings.database_url
    db_path = db_url.replace("sqlite:///", "") if db_url.startswith("sqlite:///") else db_url
    migration = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
    profile = get_or_create_company_profile(db)
    policy = get_or_create_pricing_policy(db)
    backup_dir = Path(os.getenv("BACKUP_DIR", "./backups")).resolve()
    backup_writable = backup_dir.exists() and os.access(backup_dir, os.W_OK)

    context = template_context(request, lang)
    context.update(
        {
            "diag": {
                "version": os.getenv("APP_VERSION", "local-dev"),
                "python": sys.version.split()[0],
                "env": settings.app_env,
                "db_path": db_path,
                "migration": migration or "unknown",
                "company_configured": bool(profile.legal_name),
                "pricing_configured": bool(policy.min_margin_pct is not None),
                "backup_writable": backup_writable,
                "ready": True,
            }
        }
    )
    return templates.TemplateResponse(request, "admin/diagnostics.html", context)
