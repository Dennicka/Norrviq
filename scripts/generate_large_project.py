#!/usr/bin/env python3
import argparse

from app.db import SessionLocal
from app.services.large_project import LargeProjectSpec, create_large_project


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic large project fixture")
    parser.add_argument("--rooms", type=int, default=50)
    parser.add_argument("--items", type=int, default=300)
    parser.add_argument("--name", type=str, default="Large project")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        project = create_large_project(
            db,
            spec=LargeProjectSpec(rooms_count=args.rooms, work_items_count=args.items),
            name=args.name,
        )
        print(f"Created project id={project.id} rooms={args.rooms} items={args.items}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
