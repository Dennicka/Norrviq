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
    admin_email = settings.admin_email.strip().lower()
    admin_password = settings.admin_password
    if not admin_email or not admin_password:
        return

    existing_admin = db.query(User).filter(User.email == admin_email).first()
    if existing_admin:
        return

    user = User(email=admin_email, password_hash=hash_password(admin_password), role=ADMIN_ROLE)
    db.add(user)
    db.commit()
    log_auth_event("admin_created", email=admin_email, role=ADMIN_ROLE)
