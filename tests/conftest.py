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

TEST_DB_PATH = Path(tempfile.gettempdir()) / f"norrviq-test-{uuid.uuid4().hex}.sqlite3"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ.setdefault("APP_ENV", "local")
os.environ.setdefault("SESSION_SECRET", "test-secret-key-0123456789-0123456789")
os.environ.setdefault("ALLOW_DEV_DEFAULTS", "false")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("ADMIN_BOOTSTRAP_ENABLED", "true")
os.environ.setdefault("ADMIN_EMAIL", "admin.test@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "Admin#Pass123")

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from .db_utils import upgrade_database  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.auth import create_admin_user  # noqa: E402


if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()
upgrade_database(os.environ["DATABASE_URL"])

_db = SessionLocal()
try:
    if not _db.query(User).filter(User.email == os.environ["ADMIN_EMAIL"]).first():
        create_admin_user(_db, email=os.environ["ADMIN_EMAIL"], password=os.environ["ADMIN_PASSWORD"])
finally:
    _db.close()


_ORIGINAL_TESTCLIENT_REQUEST = TestClient.request
_CSRF_META_RE = re.compile(r'<meta\s+name="csrf-token"\s+content="([^"]+)"')


def _extract_csrf_token(body: str) -> str | None:
    match = _CSRF_META_RE.search(body)
    if not match:
        return None
    return match.group(1)


def _csrf_aware_request(self, method, url, *args, **kwargs):
    if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        headers = dict(kwargs.get("headers") or {})
        if headers.pop("X-No-Auto-CSRF", None) != "1":
            data = kwargs.get("data")
            has_form_token = isinstance(data, dict) and "csrf_token" in data
            has_header_token = "X-CSRF-Token" in headers
            if not has_form_token and not has_header_token:
                token_response = _ORIGINAL_TESTCLIENT_REQUEST(self, "GET", "/login", follow_redirects=True)
                token = _extract_csrf_token(token_response.text)
                if token:
                    headers["X-CSRF-Token"] = token
                    if isinstance(data, dict):
                        kwargs["data"] = {**data, "csrf_token": token}
        kwargs["headers"] = headers
    return _ORIGINAL_TESTCLIENT_REQUEST(self, method, url, *args, **kwargs)


TestClient.request = _csrf_aware_request
