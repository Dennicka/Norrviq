from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings


def _login(client: TestClient):
    settings = get_settings()
    r = client.post('/login', data={'email': settings.admin_email, 'password': settings.admin_password}, follow_redirects=False)
    assert r.status_code in (302,303)


def test_core_pages_ru_sv_no_500():
    with TestClient(app) as client:
        _login(client)
        for lang in ('ru','sv'):
            client.get(f'/lang/{lang}?next=/', follow_redirects=False)
            for path in ('/','/projects/','/clients/','/materials/','/settings/'):
                resp = client.get(path)
                assert resp.status_code == 200
