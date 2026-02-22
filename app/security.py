import base64
import hashlib
import hmac
import logging
import secrets

from fastapi import HTTPException, Request, status

from app.config import get_settings

logger = logging.getLogger("uvicorn.error")

ADMIN_ROLE = "admin"
OPERATOR_ROLE = "operator"
VIEWER_ROLE = "viewer"
AUDITOR_ROLE = "auditor"
VALID_ROLES = {ADMIN_ROLE, OPERATOR_ROLE, VIEWER_ROLE, AUDITOR_ROLE}
CSRF_SESSION_KEY = "csrf_token"


class SecurityConfigError(RuntimeError):
    pass


def _decode_secret(value: str) -> bytes:
    try:
        return bytes.fromhex(value)
    except ValueError:
        pass
    try:
        return base64.b64decode(value, validate=True)
    except Exception:
        return value.encode("utf-8")


def validate_security_settings() -> None:
    settings = get_settings()
    if not settings.session_secret and settings.app_env == "local":
        logger.warning("SESSION_SECRET is not set in local mode; using ephemeral secret")
        return

    if not settings.session_secret:
        raise SecurityConfigError("SESSION_SECRET is required when APP_ENV is not local")

    if len(_decode_secret(settings.session_secret)) < 32:
        raise SecurityConfigError("SESSION_SECRET must be at least 32 bytes (raw/hex/base64)")


def get_current_user_email(request: Request) -> str | None:
    return request.session.get("user_email")


def get_current_user_role(request: Request) -> str | None:
    return request.session.get("user_role")


def get_current_username(request: Request) -> str | None:
    return get_current_user_email(request)


def require_auth(request: Request) -> str:
    current_user = get_current_user_email(request)
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


def require_role(*roles: str):
    allowed_roles = set(roles)

    def _role_checker(request: Request) -> str:
        require_auth(request)
        role = get_current_user_role(request)
        if role in allowed_roles:
            return role  # type: ignore[return-value]

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")

    return _role_checker


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, salt_b64, hash_b64 = password_hash.split("$", 2)
        if algorithm != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected_hash = base64.b64decode(hash_b64)
    except Exception:
        return False

    actual_hash = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return hmac.compare_digest(actual_hash, expected_hash)


def log_auth_event(event: str, **kwargs) -> None:
    safe_payload = {k: v for k, v in kwargs.items() if "password" not in k and "secret" not in k}
    logger.info("auth_event=%s payload=%s", event, safe_payload)


def ensure_csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf_token(request: Request, token: str | None) -> bool:
    if not token:
        return False
    expected = request.session.get(CSRF_SESSION_KEY)
    if not expected:
        return False
    return hmac.compare_digest(token, expected)
