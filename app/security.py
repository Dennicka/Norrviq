from typing import Optional

from fastapi import HTTPException, Request, status

from app.config import get_settings


def get_current_username(request: Request) -> Optional[str]:
    return request.session.get("user")


def require_auth(request: Request) -> str:
    current_user = get_current_username(request)
    if current_user:
        return current_user

    next_path = request.url.path
    if request.url.query:
        next_path += f"?{request.url.query}"
    redirect_url = f"/login?next={next_path}"
    raise HTTPException(
        status_code=status.HTTP_302_FOUND,
        headers={"Location": redirect_url},
    )


def authenticate_user(username: str, password: str) -> bool:
    settings = get_settings()
    return username == settings.admin_username and password == settings.admin_password
