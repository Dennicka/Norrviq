import re
from typing import Any

from fastapi.testclient import TestClient

_META_TOKEN_RE = re.compile(r'<meta\s+name="csrf-token"\s+content="([^"]+)"')
_HIDDEN_TOKEN_RE = re.compile(
    r'<input[^>]+name="csrf_token"[^>]+value="([^"]+)"|<input[^>]+value="([^"]+)"[^>]+name="csrf_token"'
)


def extract_csrf_token(html: str) -> str:
    meta_match = _META_TOKEN_RE.search(html)
    if meta_match:
        return meta_match.group(1)

    hidden_match = _HIDDEN_TOKEN_RE.search(html)
    if hidden_match:
        return hidden_match.group(1) or hidden_match.group(2)

    raise AssertionError("CSRF token not found in HTML")


def csrf_post(
    client: TestClient,
    *,
    form_url: str,
    post_url: str,
    data: dict[str, Any],
    follow_redirects: bool = False,
):
    form_response = client.get(form_url, follow_redirects=True)
    assert form_response.status_code == 200
    token = extract_csrf_token(form_response.text)
    payload = {**data, "csrf_token": token}
    return client.post(
        post_url,
        data=payload,
        headers={"X-CSRF-Token": token},
        follow_redirects=follow_redirects,
    )
