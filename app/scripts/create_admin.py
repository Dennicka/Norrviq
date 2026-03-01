import argparse
import sys

from app.db import SessionLocal
from app.services.auth import create_admin_user
from app.models.user import User
from app.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Create initial admin user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--update-password", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == args.email.strip().lower()).first()
        if existing:
            if args.update_password:
                existing.password_hash = hash_password(args.password)
                db.add(existing)
                db.commit()
                print(f"User already exists, password updated: {existing.email}")
            else:
                print("User already exists, skipping")
            return
        user = create_admin_user(db, email=args.email, password=args.password)
        print(f"Created admin user: {user.email}")
    finally:
        db.close()
    sys.exit(0)


if __name__ == "__main__":
    main()
