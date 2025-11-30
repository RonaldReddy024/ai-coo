import logging

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings


logger = logging.getLogger(__name__)


def _create_engine_with_fallback():
    """Create an engine, falling back to SQLite if Postgres is unavailable."""

    url = settings.DATABASE_URL
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)

    try:
        # Attempt an eager connection so startup fails fast with a helpful fallback.
        with engine.connect():
            return engine
    except OperationalError:
        if url.startswith("sqlite"):
            # If SQLite failed there's nothing sensible to fall back to; re-raise.
            raise

        fallback_url = "sqlite:///./app.db"
        fallback_connect_args = {"check_same_thread": False}
        logger.warning(
            "Could not connect to %s. Falling back to local SQLite database at %s.",
            url,
            fallback_url,
        )
        return create_engine(fallback_url, connect_args=fallback_connect_args)


# Create the SQLAlchemy engine with resilience for local development.
engine = _create_engine_with_fallback()

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all models
Base = declarative_base()
