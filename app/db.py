"""Database engine setup, session lifecycle, and lightweight SQLite migrations."""

from collections.abc import Callable, Generator
from dataclasses import dataclass

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.schema import CreateIndex, CreateTable

from .config import get_settings

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.db_url.startswith("sqlite") else {}
engine = create_engine(settings.db_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


if settings.db_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        """Enable SQLite foreign-key enforcement on every new connection."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


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


def _ensure_prompt_project_foreign_key(target_engine=None) -> None:
    """Rebuild legacy ``prompt_projects`` tables so their source FK is enforced.

    SQLite cannot add a foreign key with ``ALTER TABLE``. The rebuild copies all
    existing rows to a new table, drops the old one, and restores indexes. The
    operation is skipped for incomplete legacy fixtures that never had the
    current model's non-reference columns.
    """
    target_engine = target_engine or engine
    table_name = "prompt_projects"
    inspector = inspect(target_engine)
    if table_name not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    foreign_keys = inspector.get_foreign_keys(table_name)
    if any(
        fk.get("constrained_columns") == ["source_project_id"]
        and fk.get("referred_table") == "projects"
        for fk in foreign_keys
    ):
        return

    from . import models  # noqa: F401

    table = Base.metadata.tables[table_name]
    reference_columns = {
        "source_project_id",
        "reference_mode",
        "reference_snapshot_json",
        "entity_bible_json",
    }
    required_columns = {column.name for column in table.columns} - reference_columns
    if not required_columns <= existing_columns:
        return

    rebuild_name = "prompt_projects__fk_rebuild"
    create_sql = str(CreateTable(table).compile(dialect=target_engine.dialect)).strip()
    create_sql = create_sql.replace(
        f"CREATE TABLE {table.name}", f"CREATE TABLE {rebuild_name}", 1
    )
    copy_columns = [column.name for column in table.columns if column.name in existing_columns]
    column_list = ", ".join(copy_columns)

    with target_engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            with connection.begin():
                connection.exec_driver_sql(f"DROP TABLE IF EXISTS {rebuild_name}")
                connection.exec_driver_sql(create_sql)
                connection.exec_driver_sql(
                    f"INSERT INTO {rebuild_name} ({column_list}) "
                    f"SELECT {column_list} FROM {table_name}"
                )
                connection.exec_driver_sql(f"DROP TABLE {table_name}")
                connection.exec_driver_sql(
                    f"ALTER TABLE {rebuild_name} RENAME TO {table_name}"
                )
                for index in table.indexes:
                    connection.exec_driver_sql(
                        str(CreateIndex(index).compile(dialect=target_engine.dialect))
                    )
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()


@dataclass(frozen=True)
class _Migration:
    """One ordered, idempotent SQLite schema migration."""

    version: int
    name: str
    apply: Callable[[object], None]


_SQLITE_MIGRATIONS = (
    _Migration(1, "add_prompt_reference_columns", _ensure_sqlite_columns),
    _Migration(2, "enforce_prompt_source_foreign_key", _ensure_prompt_project_foreign_key),
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
