from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

from tests.e2e.csrf_helper import csrf_post


settings = get_settings()

def test_post_without_csrf_is_rejected_with_403():
    with TestClient(app) as client:
        login_response = csrf_post(
            client,
            form_url="/login",
            post_url="/login",
            data={"email": settings.admin_email, "password": settings.admin_password},
            follow_redirects=False,
        )
        assert login_response.status_code in (302, 303)
    
        response = client.post(
            "/projects/new",
            data={"name": "No CSRF Project", "status": "draft"},
            headers={"X-No-Auto-CSRF": "1"},
            follow_redirects=False,
        )
    
        assert response.status_code == 403
        assert "CSRF" in response.text
