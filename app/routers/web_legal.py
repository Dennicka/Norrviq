from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.legal_note import LegalNote

router = APIRouter(prefix="/legal-notes", tags=["legal_notes"])


@router.get("/")
async def list_legal_notes(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    notes = db.query(LegalNote).all()
    context = template_context(request, lang)
    context["notes"] = notes
    return templates.TemplateResponse("legal_notes/list.html", context)


@router.get("/new")
async def new_legal_note_form(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    context = template_context(request, lang)
    context["note"] = None
    return templates.TemplateResponse("legal_notes/form.html", context)


@router.post("/new")
async def create_legal_note(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    form = await request.form()
    note = LegalNote(
        code=form.get("code"),
        title_ru=form.get("title_ru"),
        text_ru=form.get("text_ru"),
        title_sv=form.get("title_sv"),
        text_sv=form.get("text_sv"),
    )
    db.add(note)
    db.commit()
    return RedirectResponse(url="/legal-notes/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{note_id}/edit")
async def edit_legal_note_form(
    note_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    note = db.get(LegalNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="LegalNote not found")
    context = template_context(request, lang)
    context["note"] = note
    return templates.TemplateResponse("legal_notes/form.html", context)


@router.post("/{note_id}/edit")
async def update_legal_note(
    note_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    note = db.get(LegalNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="LegalNote not found")

    form = await request.form()
    note.code = form.get("code")
    note.title_ru = form.get("title_ru")
    note.text_ru = form.get("text_ru")
    note.title_sv = form.get("title_sv")
    note.text_sv = form.get("text_sv")

    db.add(note)
    db.commit()

    return RedirectResponse(url="/legal-notes/", status_code=status.HTTP_303_SEE_OTHER)
