import logging

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

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


# One-time safe migration to add next_steps column if it doesn't exist
def ensure_next_steps_column():
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN next_steps TEXT"))
        except Exception:
            # If the column already exists or table doesn't exist yet, ignore
            pass


ensure_next_steps_column()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_sqlite_schema(engine):
    """Ensure SQLite has the columns expected by the ORM models.

    SQLite's ``CREATE TABLE IF NOT EXISTS`` does not add newly introduced
    columns. For existing local databases we opportunistically add the
    ``external_provider_status`` column so the app can start without manual
    migration steps.
    """

    if engine.url.get_backend_name() != "sqlite":
        return

    with engine.connect() as conn, conn.begin():
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(tasks);"))}

        if "external_provider_status" not in columns:
            conn.execute(
                text(
                    "ALTER TABLE tasks ADD COLUMN external_provider_status VARCHAR DEFAULT 'ok';"
                )
            )

        if "owner_email" not in columns:
            conn.execute(
                text("ALTER TABLE tasks ADD COLUMN owner_email VARCHAR;"),
            )

        if "prerequisite_task_id" not in columns:
            conn.execute(
                text("ALTER TABLE tasks ADD COLUMN prerequisite_task_id INTEGER;"),
            )

        sprint_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(sprints);"))}
        if "owner_email" not in sprint_columns:
            conn.execute(text("ALTER TABLE sprints ADD COLUMN owner_email VARCHAR;"))
        if "baseline_date" not in sprint_columns:
            conn.execute(text("ALTER TABLE sprints ADD COLUMN baseline_date DATETIME;"))
            
        project_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(projects);"))}
        if "owner_email" not in project_columns:
            conn.execute(text("ALTER TABLE projects ADD COLUMN owner_email VARCHAR;"))

        company_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(companies);"))}
        if "owner_email" not in company_columns:
            conn.execute(text("ALTER TABLE companies ADD COLUMN owner_email VARCHAR;"))

        # Opportunistically backfill a hard-coded dependency so it is explicit
        # in data instead of inferred from text alone.
        try:
            prereq = conn.execute(
                text(
                    "SELECT id FROM tasks WHERE title LIKE :title ORDER BY id DESC LIMIT 1"
                ),
                {"title": "Define Operational KPIs%"},
            ).fetchone()
            baseline = conn.execute(
                text(
                    "SELECT id, prerequisite_task_id FROM tasks WHERE title LIKE :title ORDER BY id DESC LIMIT 1"
                ),
                {"title": "Baseline KPI Analysis%"},
            ).fetchone()

            if prereq and baseline and baseline[1] is None:
                conn.execute(
                    text(
                        "UPDATE tasks SET prerequisite_task_id = :prereq_id WHERE id = :task_id"
                    ),
                    {"prereq_id": prereq[0], "task_id": baseline[0]},
                )
        except Exception:
            # If the table doesn't exist yet or titles don't match, skip silently
            pass
