"""Helper script to reset the local SQLite database.

Deletes the SQLite file configured in ``settings.DATABASE_URL`` when it is a
SQLite URL, then recreates all tables using the current SQLAlchemy models. This
is useful after adding new columns such as ``company_id`` or ``squad``.
"""
from pathlib import Path
from typing import Optional

from sqlalchemy.engine import make_url

from app import models  # noqa: F401 - ensure models are registered
from app.config import settings
from app.database import Base, engine


def resolve_sqlite_path(url: str) -> Optional[Path]:
    """Return the filesystem path for a SQLite URL or ``None`` otherwise."""

    parsed = make_url(url)
    if parsed.drivername != "sqlite":
        return None

    if parsed.database is None:
        return None

    return Path(parsed.database)


def reset_sqlite_db() -> None:
    db_path = resolve_sqlite_path(settings.DATABASE_URL)
    if db_path is None:
        raise SystemExit("DATABASE_URL is not a SQLite URL; nothing to reset.")

    if db_path.exists():
        db_path.unlink()
        print(f"Deleted existing SQLite database at {db_path}")
    else:
        print(f"No SQLite database found at {db_path}; creating a fresh one")

    Base.metadata.create_all(bind=engine)
    print("Recreated tables from current models.")


if __name__ == "__main__":
    reset_sqlite_db()
