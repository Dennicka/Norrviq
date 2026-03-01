import argparse

from app.db import SessionLocal
from app.models.user import User
from app.security import hash_password
from app.services.auth import create_admin_user


def main() -> None:
    parser = argparse.ArgumentParser(description="Create initial admin user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--update-password", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        try:
            user = create_admin_user(db, email=args.email, password=args.password)
            print(f"Created admin user: {user.email}")
            return
        except ValueError:
            existing = db.query(User).filter(User.email == args.email.strip().lower()).first()
            if existing and args.update_password:
                existing.password_hash = hash_password(args.password)
                db.add(existing)
                db.commit()
                print("User already exists, password updated")
                return
            print("User already exists, skipping")
            return
    finally:
        db.close()


if __name__ == "__main__":
    main()
