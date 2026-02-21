import os
import re
import sys

from fastapi.testclient import TestClient


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-0123456789-0123456789")
os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "admin-password")
os.environ.setdefault("ALLOW_DEV_DEFAULTS", "true")

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()


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
