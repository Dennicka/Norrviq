from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.user import User
from app.security import ADMIN_ROLE, hash_password, log_auth_event, verify_password


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    ensure_admin_user(db)
    normalized_email = email.strip().lower()
    user = db.query(User).filter(User.email == normalized_email).first()
    if not user:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user


def ensure_admin_user(db: Session) -> None:
    settings = get_settings()
    if settings.app_env != "local" or not settings.admin_bootstrap_enabled:
        return

    admin_email = settings.admin_email.strip().lower()
    admin_password = settings.admin_password
    if not admin_email or not admin_password:
        return

    existing_admin = db.query(User).filter(User.email == admin_email).first()
    if existing_admin:
        return

    create_admin_user(db, email=admin_email, password=admin_password)


def create_admin_user(db: Session, email: str, password: str) -> User:
    normalized_email = email.strip().lower()
    existing_admin = db.query(User).filter(User.email == normalized_email).first()
    if existing_admin:
        raise ValueError(f"User already exists: {normalized_email}")

    user = User(email=normalized_email, password_hash=hash_password(password), role=ADMIN_ROLE)
    db.add(user)
    db.commit()
    db.refresh(user)
    log_auth_event("admin_created", email=normalized_email, role=ADMIN_ROLE)
    return user
