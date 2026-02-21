#!/usr/bin/env python3
from alembic import command
from alembic.config import Config


def main() -> None:
    command.current(Config("alembic.ini"), verbose=True)


if __name__ == "__main__":
    main()
