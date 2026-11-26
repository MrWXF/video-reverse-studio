import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes
from app.config import Settings, get_settings
from app.db import Base, get_db
from app.main import app
from app.models import Project, Shot


@pytest.fixture
def media_client(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    get_settings.cache_clear()
    settings = Settings(data_dir=tmp_path, app_password="")
    monkeypatch.setattr(routes, "get_settings", lambda: settings)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    project_id = "project-1"
    project_dir = tmp_path / "projects" / project_id
    frames_dir = project_dir / "frames"
    frames_dir.mkdir(parents=True)
    source = project_dir / "source.mp4"
    source.write_bytes(b"video-bytes")
    keyframe = frames_dir / "shot_0001.jpg"
    keyframe.write_bytes(b"jpeg-bytes")

    with testing_session() as db:
        db.add(
            Project(
                id=project_id,
                title="测试项目",
                source_path=str(source),
                status="done",
            )
        )
        db.add(
            Shot(
                id=1,
                project_id=project_id,
                index=1,
                start_s=0.0,
                end_s=1.0,
                keyframe_path="projects/project-1/frames/shot_0001.jpg",
            )
        )
        db.commit()

    def override_db():
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    yield TestClient(app), project_id
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_video_route_serves_project_source(media_client):
    client, project_id = media_client
    response = client.get(f"/api/projects/{project_id}/video")
    assert response.status_code == 200
    assert response.content == b"video-bytes"
    assert response.headers["content-type"].startswith("video/mp4")


def test_keyframe_route_serves_project_frame(media_client):
    client, project_id = media_client
    response = client.get(f"/api/projects/{project_id}/shots/1/keyframe")
    assert response.status_code == 200
    assert response.content == b"jpeg-bytes"
    assert response.headers["content-type"].startswith("image/jpeg")


def test_video_route_supports_byte_ranges_for_seeking(media_client):
    client, project_id = media_client
    response = client.get(
        f"/api/projects/{project_id}/video",
        headers={"Range": "bytes=0-4"},
    )

    assert response.status_code == 206
    assert response.content == b"video"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-range"] == "bytes 0-4/11"
    assert response.headers["content-length"] == "5"


def test_video_route_supports_suffix_and_open_ended_ranges(media_client):
    client, project_id = media_client
    url = f"/api/projects/{project_id}/video"

    suffix = client.get(url, headers={"Range": "bytes=-5"})
    assert suffix.status_code == 206
    assert suffix.content == b"bytes"
    assert suffix.headers["content-range"] == "bytes 6-10/11"

    open_ended = client.get(url, headers={"Range": "bytes=6-"})
    assert open_ended.status_code == 206
    assert open_ended.content == b"bytes"


def test_video_route_rejects_unsatisfiable_range(media_client):
    client, project_id = media_client
    response = client.get(
        f"/api/projects/{project_id}/video",
        headers={"Range": "bytes=99-"},
    )

    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */11"


def test_keyframe_route_supports_ranges(media_client):
    client, project_id = media_client
    response = client.get(
        f"/api/projects/{project_id}/shots/1/keyframe",
        headers={"Range": "bytes=0-3"},
    )
    assert response.status_code == 206
    assert response.content == b"jpeg"


def test_project_media_path_rejects_files_outside_project(tmp_path):
    settings = Settings(data_dir=tmp_path)
    outside = tmp_path / "app.db"
    outside.write_bytes(b"database")

    with pytest.raises(HTTPException) as exc_info:
        routes._project_media_path("project-1", str(outside), settings)

    assert exc_info.value.status_code == 404


def test_project_media_path_accepts_relative_project_file(tmp_path):
    settings = Settings(data_dir=tmp_path)
    root = tmp_path / "projects" / "project-1"
    root.mkdir(parents=True)
    source = root / "source.mp4"
    source.write_bytes(b"video")

    assert routes._project_media_path(
        "project-1", "projects/project-1/source.mp4", settings
    ) == source.resolve()
