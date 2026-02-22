from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import add_flash_message, get_current_lang, get_db, template_context, templates
from app.security import require_role
from app.services.backup import (
    backup_file_path,
    create_backup,
    delete_backup,
    get_backup_or_404,
    list_backups,
    restore_backup,
    verify_backup_checksum,
)

router = APIRouter(prefix="/admin/backups", tags=["backups"])


@router.get("")
async def backups_page(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang), _role: str = Depends(require_role("admin", "auditor"))):
    context = template_context(request, lang)
    context.update({"backups": list_backups(db)})
    return templates.TemplateResponse(request, "admin/backups.html", context)


@router.post("/create")
async def backups_create(request: Request, db: Session = Depends(get_db), _role: str = Depends(require_role("admin"))):
    create_backup(db, request.session.get("user_email"))
    add_flash_message(request, "Backup created", "success")
    return RedirectResponse("/admin/backups", status_code=303)


@router.get("/{backup_id}/download")
async def backups_download(backup_id: int, db: Session = Depends(get_db), _role: str = Depends(require_role("admin", "auditor"))):
    row = get_backup_or_404(db, backup_id)
    path = backup_file_path(row.filename)
    return FileResponse(path, filename=row.filename, media_type="application/octet-stream")


@router.post("/{backup_id}/verify")
async def backups_verify(backup_id: int, request: Request, db: Session = Depends(get_db), _role: str = Depends(require_role("admin", "auditor"))):
    ok = verify_backup_checksum(db, backup_id, request.session.get("user_email"))
    add_flash_message(request, "Checksum verified" if ok else "Checksum mismatch", "success" if ok else "error")
    return RedirectResponse("/admin/backups", status_code=303)


@router.post("/{backup_id}/delete")
async def backups_delete(backup_id: int, request: Request, db: Session = Depends(get_db), _role: str = Depends(require_role("admin"))):
    delete_backup(db, backup_id, request.session.get("user_email"))
    add_flash_message(request, "Backup deleted", "success")
    return RedirectResponse("/admin/backups", status_code=303)


@router.post("/restore")
async def backups_restore(
    request: Request,
    db: Session = Depends(get_db),
    upload_db: UploadFile = File(...),
    upload_sha256: Annotated[UploadFile | None, File()] = None,
    confirmation_word: str = Form(...),
    _role: str = Depends(require_role("admin")),
):
    restore_backup(db, getattr(request.state, "request_id", None), request.session.get("user_email"), upload_db, confirmation_word, upload_sha256=upload_sha256)
    add_flash_message(request, "Restore finished", "success")
    return RedirectResponse("/admin/backups", status_code=303)
