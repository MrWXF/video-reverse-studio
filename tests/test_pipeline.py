import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base
from app.models import Job, Project, Shot
from app.services import capacity, media, pipeline


@pytest.fixture
def pipeline_env(tmp_path, monkeypatch):
    settings = Settings(
        data_dir=tmp_path,
        llm_provider="mock",
        llm_api_key="",
        asr_provider="none",
        retry_max_attempts=3,
        retry_base_delay_s=0.0,
        retry_max_delay_s=0.0,
        max_active_jobs=2,
    )
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    source = tmp_path / "projects" / "project-1" / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"\x00\x00\x00\x18ftypmp42source")
    with testing_session() as db:
        db.add(
            Project(
                id="project-1",
                title="流水线测试",
                source_path=str(source),
                status="queued",
            )
        )
        db.add(Job(id="job-1", project_id="project-1", status="queued", step="queued"))
        db.commit()

    def fake_extract(ffmpeg, video, timestamp, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"jpeg")

    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    monkeypatch.setattr(pipeline, "SessionLocal", testing_session)
    monkeypatch.setattr(
        media,
        "probe",
        lambda path, cfg: media.VideoMeta(
            duration=4.0, width=640, height=360, fps=24.0
        ),
    )
    monkeypatch.setattr(
        media,
        "detect_shots",
        lambda path, meta, cfg: [(0.0, 2.0), (2.0, 4.0)],
    )
    monkeypatch.setattr(media, "resolve_ffmpeg", lambda configured: "ffmpeg")
    monkeypatch.setattr(media, "extract_keyframe", fake_extract)
    capacity.reset_for_tests()
    yield settings, testing_session, tmp_path
    capacity.reset_for_tests()


def test_pipeline_completes_and_writes_recipe_assets(pipeline_env):
    settings, testing_session, data_dir = pipeline_env

    pipeline.run_pipeline("project-1", "job-1", request_id="trace-pipeline-1")

    with testing_session() as db:
        project = db.get(Project, "project-1")
        job = db.get(Job, "job-1")
        shots = db.query(Shot).order_by(Shot.index).all()
        assert project.status == "done"
        assert job.status == "done"
        assert job.step == "done"
        assert job.metrics["request_id"] == "trace-pipeline-1"
        assert job.metrics["analysis_mode"] == "mock"
        assert job.metrics["degraded"] is False
        assert job.metrics["asr_status"] == "disabled"
        assert [shot.index for shot in shots] == [1, 2]
        assert all(shot.confidence > 0 for shot in shots)
    output = data_dir / "projects" / "project-1" / "output"
    assert (output / "video.md").exists()
    assert (output / "video.json").exists()
    assert capacity.active_jobs() == 0


def test_pipeline_retries_transient_failures(pipeline_env, monkeypatch):
    _, testing_session, _ = pipeline_env
    original = pipeline._execute
    calls = 0

    def flaky(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("temporary upstream disconnect")
        return original(*args)

    monkeypatch.setattr(pipeline, "_execute", flaky)
    pipeline.run_pipeline("project-1", "job-1")

    with testing_session() as db:
        assert db.get(Job, "job-1").status == "done"
    assert calls == 2


def test_pipeline_redacts_paths_and_credentials_on_failure(pipeline_env, monkeypatch):
    settings, testing_session, data_dir = pipeline_env
    settings.retry_max_attempts = 1

    def fail(*_args):
        raise RuntimeError(
            f"cannot read {data_dir / 'projects' / 'secret.mp4'} with sk-supersecret123"
        )

    monkeypatch.setattr(pipeline, "_execute", fail)
    pipeline.run_pipeline("project-1", "job-1")

    with testing_session() as db:
        job = db.get(Job, "job-1")
        assert job.status == "failed"
        assert str(data_dir) not in job.error
        assert "sk-supersecret123" not in job.error
        assert "<DATA_DIR>" in job.error
    assert capacity.active_jobs() == 0


def test_pipeline_rejects_when_global_capacity_is_full(pipeline_env):
    settings, testing_session, _ = pipeline_env
    settings.max_active_jobs = 1
    assert capacity.acquire_job(1)

    pipeline.run_pipeline("project-1", "job-1")

    with testing_session() as db:
        job = db.get(Job, "job-1")
        assert job.status == "failed"
        assert "并发" in job.error
    capacity.release_job()
    assert capacity.active_jobs() == 0
