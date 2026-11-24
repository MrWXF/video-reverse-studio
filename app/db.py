from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.db_url.startswith("sqlite") else {}
engine = create_engine(settings.db_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        _ensure_sqlite_columns()


def _ensure_sqlite_columns(target_engine=None) -> None:
    """Apply additive migrations for existing SQLite databases."""
    target_engine = target_engine or engine
    table = "prompt_projects"
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


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
