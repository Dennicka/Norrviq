from __future__ import annotations

from io import BytesIO
import importlib.util

from fastapi.testclient import TestClient
import pytest

from app.config import get_settings
from app.main import app
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

    if kind == "offer":
        response = client.get(f"/offers/{fixture.project_id}/pdf")
        expected_header = "Offert"
        doc_number = None
    else:
        response = client.get(f"/invoices/{fixture.invoice_id}/pdf")
        expected_header = "Faktura"
        doc_number = "TR-" if issue_documents else None

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")

    pdf_text = _extract_pdf_text(response.content)
    assert expected_header in pdf_text
    assert "Moms" in pdf_text
    if kind == "invoice" and enable_rot:
        assert "ROT-avdrag" in pdf_text
    if doc_number:
        assert doc_number in pdf_text
