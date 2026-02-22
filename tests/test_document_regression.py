from __future__ import annotations

from io import BytesIO
import importlib.util

from fastapi.testclient import TestClient
import pytest

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.company_profile import get_or_create_company_profile
from tests.utils.document_factory import create_stable_document_fixture
from tests.utils.pdf_text import norm_pdf_text
from tests.utils.snapshot import assert_matches_snapshot, normalize_document_html

client = TestClient(app)
settings = get_settings()

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("weasyprint") is None or importlib.util.find_spec("pypdf") is None,
    reason="PDF dependencies are not installed in this environment",
)


def _login() -> None:
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def _extract_pdf_text(content: bytes) -> str:
    reader = pytest.importorskip("pypdf").PdfReader(BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


@pytest.mark.parametrize(
    ("path", "snapshot_name", "pricing_mode", "enable_rot"),
    [
        ("/projects/{project_id}/offer?lang=sv", "offer_draft.html", "HOURLY", False),
        ("/projects/{project_id}/offer?lang=sv", "offer_issued_fixed_total.html", "FIXED_TOTAL", False),
        ("/projects/{project_id}/offer?lang=sv", "offer_issued_per_m2.html", "PER_M2", False),
        ("/projects/{project_id}/offer?lang=sv", "offer_issued_per_room.html", "PER_ROOM", False),
        ("/projects/{project_id}/offer?lang=sv", "offer_issued_piecework.html", "PIECEWORK", False),
        ("/projects/{project_id}/invoices/{invoice_id}", "invoice_draft.html", "HOURLY", False),
        ("/projects/{project_id}/invoices/{invoice_id}", "invoice_issued_fixed_total_rot_off.html", "FIXED_TOTAL", False),
        ("/projects/{project_id}/invoices/{invoice_id}", "invoice_issued_per_m2_rot_off.html", "PER_M2", False),
        ("/projects/{project_id}/invoices/{invoice_id}", "invoice_issued_per_room_rot_off.html", "PER_ROOM", False),
        ("/projects/{project_id}/invoices/{invoice_id}", "invoice_issued_piecework_rot_on.html", "PIECEWORK", True),
    ],
)
def test_document_html_snapshots(path: str, snapshot_name: str, pricing_mode: str, enable_rot: bool) -> None:
    _login()

    fixture = create_stable_document_fixture(
        enable_rot=enable_rot,
        issue_documents="issued" in snapshot_name,
        pricing_mode=pricing_mode,
    )
    url = path.format(project_id=fixture.project_id, invoice_id=fixture.invoice_id)

    response = client.get(url)

    assert response.status_code == 200
    normalized = normalize_document_html(response.text)
    assert_matches_snapshot(snapshot_name, normalized)


@pytest.mark.parametrize(
    ("kind", "pricing_mode", "enable_rot"),
    [
        ("offer", "FIXED_TOTAL", False),
        ("offer", "PER_M2", False),
        ("invoice", "FIXED_TOTAL", False),
        ("invoice", "PER_M2", True),
    ],
)
def test_document_pdf_smoke_issued_modes(kind: str, pricing_mode: str, enable_rot: bool) -> None:
    _login()
    fixture = create_stable_document_fixture(enable_rot=enable_rot, issue_documents=True, pricing_mode=pricing_mode)

    db = SessionLocal()
    try:
        profile = get_or_create_company_profile(db)
        offer_prefix = profile.offer_prefix or "OF-"
        invoice_prefix = profile.invoice_prefix or "TR-"
    finally:
        db.close()

    if kind == "offer":
        response = client.get(f"/offers/{fixture.project_id}/pdf")
    else:
        response = client.get(f"/invoices/{fixture.invoice_id}/pdf")

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")

    pdf_text = _extract_pdf_text(response.content)
    compact_text = norm_pdf_text(pdf_text)
    assert norm_pdf_text("Trenor Måleri AB") in compact_text

    if kind == "offer":
        assert norm_pdf_text("Offert") in compact_text or norm_pdf_text("Kommersiellt erbjudande") in compact_text
        assert norm_pdf_text(offer_prefix) in compact_text
    else:
        assert norm_pdf_text("Faktura") in compact_text
        assert norm_pdf_text("Moms") in compact_text
        assert norm_pdf_text(invoice_prefix) in compact_text
        if enable_rot:
            assert norm_pdf_text("ROT-avdrag") in compact_text

    totals_by_mode = {"FIXED_TOTAL": "8937", "PER_M2": "29046"}
    if kind == "invoice" and enable_rot and pricing_mode == "PER_M2":
        assert norm_pdf_text("22075") in compact_text
    else:
        assert norm_pdf_text(totals_by_mode[pricing_mode]) in compact_text
