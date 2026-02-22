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
    ("path", "snapshot_name"),
    [
        ("/projects/{project_id}/offer?lang=sv", "offer_draft.html"),
        ("/projects/{project_id}/offer?lang=sv", "offer_issued.html"),
        ("/projects/{project_id}/invoices/{invoice_id}", "invoice_draft.html"),
        ("/projects/{project_id}/invoices/{invoice_id}", "invoice_issued_rot_off.html"),
        ("/projects/{project_id}/invoices/{invoice_id}", "invoice_issued_rot_on.html"),
    ],
)
def test_document_html_snapshots(path: str, snapshot_name: str) -> None:
    _login()

    fixture = create_stable_document_fixture(
        enable_rot=snapshot_name.endswith("rot_on.html"),
        issue_documents="issued" in snapshot_name,
    )
    url = path.format(project_id=fixture.project_id, invoice_id=fixture.invoice_id)

    response = client.get(url)

    assert response.status_code == 200
    normalized = normalize_document_html(response.text)
    assert_matches_snapshot(snapshot_name, normalized)


@pytest.mark.parametrize(
    ("kind", "issue_documents", "enable_rot"),
    [
        ("offer", False, False),
        ("offer", True, False),
        ("invoice", False, False),
        ("invoice", True, False),
        ("invoice", True, True),
    ],
)
def test_document_pdf_smoke(kind: str, issue_documents: bool, enable_rot: bool) -> None:
    _login()
    fixture = create_stable_document_fixture(enable_rot=enable_rot, issue_documents=issue_documents)

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
    assert "Trenor Måleri AB" in pdf_text

    if kind == "offer":
        assert "Offert" in pdf_text or "Kommersiellt erbjudande" in pdf_text
        if issue_documents:
            assert offer_prefix in pdf_text
        else:
            assert "DRAFT" in pdf_text or "UTKAST" in pdf_text
        return

    assert "Faktura" in pdf_text
    assert "Moms" in pdf_text
    assert invoice_prefix in pdf_text
    if enable_rot:
        assert "ROT-avdrag" in pdf_text
