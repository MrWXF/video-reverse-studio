from sqlalchemy import create_engine, inspect, text

from app.db import _ensure_sqlite_columns


def test_sqlite_migration_adds_reference_columns_without_losing_rows(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE prompt_projects (
                    id VARCHAR(36) PRIMARY KEY,
                    title VARCHAR(200) NOT NULL,
                    brief_json JSON DEFAULT '{}',
                    plan_json JSON DEFAULT '{}',
                    status VARCHAR(30) DEFAULT 'queued',
                    step VARCHAR(50) DEFAULT 'queued',
                    progress FLOAT DEFAULT 0,
                    error TEXT DEFAULT '',
                    metrics JSON DEFAULT '{}',
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO prompt_projects (id, title, status) "
                "VALUES ('legacy', '旧方案', 'done')"
            )
        )

    _ensure_sqlite_columns(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("prompt_projects")}
    assert {
        "source_project_id",
        "reference_mode",
        "reference_snapshot_json",
        "entity_bible_json",
    } <= columns
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT id, title, reference_mode FROM prompt_projects")
        ).one()
    assert tuple(row) == ("legacy", "旧方案", "style")
