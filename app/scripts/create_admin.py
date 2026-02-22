import argparse

from app.db import SessionLocal
from app.services.auth import create_admin_user


def main() -> None:
    parser = argparse.ArgumentParser(description="Create initial admin user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = create_admin_user(db, email=args.email, password=args.password)
    finally:
        db.close()

    print(f"Created admin user: {user.email}")


if __name__ == "__main__":
    main()
