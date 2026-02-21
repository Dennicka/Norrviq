#!/usr/bin/env python3
from alembic import command
from alembic.config import Config


def main() -> None:
    command.downgrade(Config("alembic.ini"), "-1")


if __name__ == "__main__":
    main()
