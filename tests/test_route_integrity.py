from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings


def _login(client: TestClient):
    settings = get_settings()
    r = client.post('/login', data={'email': settings.admin_email, 'password': settings.admin_password}, follow_redirects=False)
    assert r.status_code in (302,303)


def test_major_routes_and_menu_links_resolve():
    with TestClient(app) as client:
        _login(client)
        paths = [
            '/', '/projects/', '/clients/', '/materials/', '/settings/', '/help/', '/admin/backups', '/admin/diagnostics'
        ]
        for path in paths:
            resp = client.get(path, follow_redirects=False)
            assert resp.status_code in (200, 302, 303), path


def test_project_workflow_links_resolve():
    with TestClient(app) as client:
        _login(client)
        p = client.post('/projects/new', data={'name':'Route Integrity Project','status':'draft'}, follow_redirects=False)
        assert p.status_code == 303
        project_id = int(p.headers['location'].rstrip('/').split('/')[-1])
        for path in [f'/projects/{project_id}', f'/projects/{project_id}/workflow', f'/projects/{project_id}/pricing', f'/projects/{project_id}/rooms/', f'/projects/{project_id}/offer']:
            resp = client.get(path, follow_redirects=False)
            assert resp.status_code in (200,302,303), path
