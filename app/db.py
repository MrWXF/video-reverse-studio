"""Database engine setup, session lifecycle, and lightweight SQLite migrations."""

from collections.abc import Callable, Generator
from dataclasses import dataclass

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.db_url.startswith("sqlite") else {}
engine = create_engine(settings.db_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base shared by all persisted models."""

    pass


def init_db() -> None:
    """Create missing tables and apply lightweight SQLite migrations on startup."""
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        _apply_sqlite_migrations()


def _ensure_sqlite_columns(target_engine=None) -> None:
    """Add the reference columns used by prompt plans.

    The function is intentionally idempotent so it can also be called directly
    by migration tooling or maintenance scripts.
    """
    target_engine = target_engine or engine
    table = "prompt_projects"
    if table not in inspect(target_engine).get_table_names():
        return
    columns = {column["name"] for column in inspect(target_engine).get_columns(table)}
    additions = {
        "source_project_id": "VARCHAR(36)",
        "reference_mode": "VARCHAR(20) DEFAULT 'style'",
        "reference_snapshot_json": "JSON DEFAULT '{}'",
        "entity_bible_json": "JSON DEFAULT '{}'",
    }
    with target_engine.begin() as connection:
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
                )


@dataclass(frozen=True)
class _Migration:
    """One ordered, idempotent SQLite schema migration."""

    version: int
    name: str
    apply: Callable[[object], None]


_SQLITE_MIGRATIONS = (
    _Migration(1, "add_prompt_reference_columns", _ensure_sqlite_columns),
)


def _apply_sqlite_migrations(target_engine=None) -> list[int]:
    """Apply pending SQLite migrations once and record their versions."""
    target_engine = target_engine or engine
    with target_engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
    with target_engine.connect() as connection:
        applied = {
            int(row[0])
            for row in connection.execute(text("SELECT version FROM schema_migrations"))
        }

    newly_applied: list[int] = []
    for migration in _SQLITE_MIGRATIONS:
        if migration.version in applied:
            continue
        migration.apply(target_engine)
        with target_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT OR IGNORE INTO schema_migrations (version, name) "
                    "VALUES (:version, :name)"
                ),
                {"version": migration.version, "name": migration.name},
            )
        newly_applied.append(migration.version)
    return newly_applied


def get_db() -> Generator[Session, None, None]:
    """Yield one request-scoped session and always close it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
