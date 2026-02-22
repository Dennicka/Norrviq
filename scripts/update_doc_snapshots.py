from __future__ import annotations

import os
import re
import sys
import tempfile
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TEST_DB_PATH = Path(tempfile.gettempdir()) / f"norrviq-doc-snapshot-{uuid.uuid4().hex}.sqlite3"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_DB_PATH}")
os.environ.setdefault("APP_ENV", "local")
os.environ.setdefault("SESSION_SECRET", "snapshot-script-secret-0123456789-0123456789")
os.environ.setdefault("ALLOW_DEV_DEFAULTS", "false")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("ADMIN_BOOTSTRAP_ENABLED", "true")
os.environ.setdefault("ADMIN_EMAIL", "admin.test@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "Admin#Pass123")

CSRF_META_RE = re.compile(r'<meta\s+name="csrf-token"\s+content="([^"]+)"')

CASES = [
    ("offer_draft.html", "/projects/{project_id}/offer?lang=sv", False, False),
    ("offer_issued.html", "/projects/{project_id}/offer?lang=sv", True, False),
    ("invoice_draft.html", "/projects/{project_id}/invoices/{invoice_id}", False, False),
    ("invoice_issued_rot_off.html", "/projects/{project_id}/invoices/{invoice_id}", True, False),
    ("invoice_issued_rot_on.html", "/projects/{project_id}/invoices/{invoice_id}", True, True),
]


def main() -> None:
    from app.config import get_settings
    from app.main import app
    from tests.db_utils import upgrade_database
    from tests.utils.document_factory import create_stable_document_fixture
    from tests.utils.snapshot import SNAPSHOT_DIR, normalize_document_html

    get_settings.cache_clear()
    upgrade_database(os.environ["DATABASE_URL"])

    client = TestClient(app)
    settings = get_settings()

    def login() -> None:
        page = client.get("/login")
        token = CSRF_META_RE.search(page.text).group(1)
        client.post(
            "/login",
            data={"username": settings.admin_email, "password": settings.admin_password, "csrf_token": token},
            headers={"X-CSRF-Token": token},
        )

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    login()

    for snapshot_name, path_tmpl, issue_documents, enable_rot in CASES:
        fixture = create_stable_document_fixture(enable_rot=enable_rot, issue_documents=issue_documents)
        path = path_tmpl.format(project_id=fixture.project_id, invoice_id=fixture.invoice_id)
        response = client.get(path)
        response.raise_for_status()

        normalized = normalize_document_html(response.text)
        (SNAPSHOT_DIR / snapshot_name).write_text(normalized, encoding="utf-8")
        print(f"updated {snapshot_name}")


if __name__ == "__main__":
    main()
