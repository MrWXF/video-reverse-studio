from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import security
from app.api import routes
from app.config import Settings, get_settings
from app.db import Base, get_db
from app.main import app
from app.models import Job, Project, PromptProject, Shot, ShotEditEvent
from app.schemas import ShotAnalysis
from app.services import capacity, media, timeline


@pytest.fixture
def timeline_env(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    get_settings.cache_clear()
    settings = Settings(
        data_dir=tmp_path,
        app_password="",
        llm_provider="mock",
        llm_api_key="",
        asr_provider="none",
        min_shot_seconds=0.8,
        max_active_jobs=2,
    )
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    source = tmp_path / "projects" / "project-1" / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"\x00\x00\x00\x18ftypmp42source")
    with testing_session() as db:
        project = Project(
            id="project-1",
            title="时间轴测试",
            source_path=str(source),
            status="done",
            duration=6.0,
            width=640,
            height=360,
            fps=24.0,
        )
        db.add(project)
        db.add_all(
            [
                Shot(
                    project_id=project.id,
                    index=1,
                    start_s=0.0,
                    end_s=2.0,
                    transcript="one",
                    origin="filmed",
                    confidence=0.8,
                    analysis={"subject": "one"},
                ),
                Shot(
                    project_id=project.id,
                    index=2,
                    start_s=2.0,
                    end_s=4.0,
                    transcript="two",
                    origin="filmed",
                    confidence=0.7,
                    analysis={"subject": "two"},
                ),
                Shot(
                    project_id=project.id,
                    index=3,
                    start_s=4.0,
                    end_s=6.0,
                    transcript="three",
                    origin="filmed",
                    confidence=0.6,
                    analysis={"subject": "three"},
                ),
            ]
        )
        db.flush()
        shot_ids = list(
            db.scalars(select(Shot.id).where(Shot.project_id == project.id).order_by(Shot.index))
        )
        db.add(
            PromptProject(
                id="prompt-1",
                title="关联提示词",
                source_project_id=project.id,
                plan_json={"warnings": ["existing"], "shots": []},
                status="done",
            )
        )
        db.commit()

    monkeypatch.setattr(timeline, "SessionLocal", testing_session)
    monkeypatch.setattr(timeline, "get_settings", lambda: settings)
    capacity.reset_for_tests()
    yield settings, testing_session, shot_ids
    capacity.reset_for_tests()
    get_settings.cache_clear()


@pytest.fixture
def timeline_client(timeline_env, monkeypatch):
    settings, testing_session, shot_ids = timeline_env

    def override_db():
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    yield TestClient(app), testing_session, shot_ids
    app.dependency_overrides.clear()


def _shots(session_factory) -> list[Shot]:
    with session_factory() as db:
        return list(db.scalars(select(Shot).order_by(Shot.index)).all())


def test_boundary_updates_both_shots_and_invalidates_prompt_mapping(timeline_env):
    settings, testing_session, shot_ids = timeline_env

    with testing_session() as db:
        project = db.get(Project, "project-1")
        mutation = timeline.update_boundary(db, project, shot_ids[0], 1.25, settings)

        shots = list(db.scalars(select(Shot).order_by(Shot.index)).all())
        assert [(shot.start_s, shot.end_s) for shot in shots[:2]] == [
            (0.0, 1.25),
            (1.25, 4.0),
        ]
        assert mutation.action == "boundary"
        assert mutation.affected_shot_ids == shot_ids[:2]
        assert mutation.prompt_projects_invalidated == 1
        assert project.status == "queued"

        job = db.get(Job, mutation.job_id)
        assert job.status == "queued"
        assert job.step == "timeline_queued"
        assert job.metrics["shot_ids"] == shot_ids[:2]

        prompt = db.get(PromptProject, "prompt-1")
        assert prompt.plan_json["warnings"] == [
            "existing",
            timeline.TIMELINE_MAPPING_WARNING,
        ]
        events = list(db.scalars(select(ShotEditEvent).order_by(ShotEditEvent.id)).all())
        assert [event.source for event in events] == ["timeline_boundary", "timeline_boundary"]
        assert [event.changes for event in events] == [
            {"end_s": {"before": 2.0, "after": 1.25}},
            {"start_s": {"before": 2.0, "after": 1.25}},
        ]


def test_boundary_rejects_short_shots_and_last_shot(timeline_env):
    settings, testing_session, shot_ids = timeline_env

    with testing_session() as db:
        project = db.get(Project, "project-1")
        with pytest.raises(timeline.TimelineValidationError, match="0.800s"):
            timeline.update_boundary(db, project, shot_ids[0], 0.2, settings)
        with pytest.raises(timeline.TimelineValidationError, match="最后一个镜头"):
            timeline.update_boundary(db, project, shot_ids[-1], 5.0, settings)
        with pytest.raises(timeline.TimelineValidationError, match="没有变化"):
            timeline.update_boundary(db, project, shot_ids[0], 2.0, settings)
        assert db.scalar(select(Job)) is None


def test_split_creates_continuous_shot_and_renumbers_following_shots(timeline_env):
    settings, testing_session, shot_ids = timeline_env

    with testing_session() as db:
        project = db.get(Project, "project-1")
        mutation = timeline.split_shot(db, project, shot_ids[0], 1.0, settings)

        shots = list(db.scalars(select(Shot).order_by(Shot.index)).all())
        assert [shot.index for shot in shots] == [1, 2, 3, 4]
        assert [(shot.start_s, shot.end_s) for shot in shots] == [
            (0.0, 1.0),
            (1.0, 2.0),
            (2.0, 4.0),
            (4.0, 6.0),
        ]
        assert mutation.action == "split"
        assert mutation.affected_shot_ids == [shot_ids[0], shots[1].id]
        assert shots[1].transcript == ""
        assert shots[1].keyframe_path == ""
        assert timeline.SPLIT_PENDING_NOTE in shots[1].analysis["evidence"]
        assert db.get(Job, mutation.job_id).metrics["shot_ids"] == mutation.affected_shot_ids


def test_merge_requires_adjacent_shots_and_keeps_left_identity(timeline_env):
    settings, testing_session, shot_ids = timeline_env

    with testing_session() as db:
        project = db.get(Project, "project-1")
        with pytest.raises(timeline.TimelineValidationError, match="相邻"):
            timeline.merge_shots(db, project, [shot_ids[0], shot_ids[2]], settings)

        mutation = timeline.merge_shots(db, project, [shot_ids[2], shot_ids[1]], settings)
        shots = list(db.scalars(select(Shot).order_by(Shot.index)).all())
        assert [shot.index for shot in shots] == [1, 2]
        assert [shot.id for shot in shots] == [shot_ids[0], shot_ids[1]]
        assert shots[1].start_s == 2.0
        assert shots[1].end_s == 6.0
        assert shots[1].transcript == "two three"
        assert db.get(Shot, shot_ids[2]) is None
        assert mutation.action == "merge"
        assert mutation.affected_shot_ids == [shot_ids[1]]
        assert timeline.MERGE_PENDING_NOTE in shots[1].analysis["evidence"]


def test_single_shot_reanalysis_only_targets_requested_shot(timeline_env):
    settings, testing_session, shot_ids = timeline_env

    with testing_session() as db:
        project = db.get(Project, "project-1")
        mutation = timeline.queue_reanalysis(db, project, shot_ids[1], settings)
        assert mutation.affected_shot_ids == [shot_ids[1]]
        prompt = db.get(PromptProject, "prompt-1")
        assert timeline.SHOT_ANALYSIS_WARNING in prompt.plan_json["warnings"]


def test_timeline_mutations_reject_busy_project_active_job_and_capacity(
    timeline_env, monkeypatch
):
    settings, testing_session, shot_ids = timeline_env

    with testing_session() as db:
        project = db.get(Project, "project-1")
        project.status = "running"
        db.commit()
        with pytest.raises(timeline.TimelineConflictError, match="正在分析"):
            timeline.queue_reanalysis(db, project, shot_ids[0], settings)

        project.status = "done"
        db.add(
            Job(
                id="active-job",
                project_id=project.id,
                status="queued",
                step="queued",
            )
        )
        db.commit()
        with pytest.raises(timeline.TimelineConflictError, match="已有活动任务"):
            timeline.queue_reanalysis(db, project, shot_ids[0], settings)

        active = db.get(Job, "active-job")
        active.status = "done"
        db.commit()
        monkeypatch.setattr(timeline.capacity, "has_capacity", lambda _limit: False)
        with pytest.raises(timeline.TimelineCapacityError, match="并发上限"):
            timeline.queue_reanalysis(db, project, shot_ids[0], settings)


def test_timeline_background_reanalysis_refreshes_only_affected_shot(
    timeline_env, monkeypatch
):
    settings, testing_session, shot_ids = timeline_env
    analyzed: list[tuple[int, Path]] = []
    extracted: list[Path] = []
    rebuilt: list[str] = []

    with testing_session() as db:
        project = db.get(Project, "project-1")
        mutation = timeline.queue_reanalysis(db, project, shot_ids[0], settings)

    def fake_extract(_ffmpeg, _source, _timestamp, output):
        extracted.append(Path(output))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"jpeg")

    def fake_analyze(_gateway, frame, index, _start, _end, _transcript, _meta):
        analyzed.append((index, Path(frame)))
        return ShotAnalysis(
            shot_type=f"type-{index}",
            subject=f"updated-{index}",
            origin="filmed",
            confidence=0.95,
            evidence=["fresh"],
        )

    def fake_rebuild(project, _settings):
        rebuilt.append(project.id)

    monkeypatch.setattr(
        media,
        "probe",
        lambda _path, _settings: media.VideoMeta(
            duration=6.0, width=640, height=360, fps=24.0
        ),
    )
    monkeypatch.setattr(media, "resolve_ffmpeg", lambda _configured: "ffmpeg")
    monkeypatch.setattr(media, "extract_keyframe", fake_extract)
    monkeypatch.setattr(timeline.vision, "analyze_shot", fake_analyze)
    monkeypatch.setattr(timeline, "rebuild_project_recipe", fake_rebuild)

    timeline.run_timeline_reanalysis("project-1", mutation.job_id, [shot_ids[0]])

    assert analyzed == [(1, extracted[0])]
    assert extracted[0].name == f"shot_{shot_ids[0]:06d}.jpg"
    assert rebuilt == ["project-1"]
    with testing_session() as db:
        job = db.get(Job, mutation.job_id)
        project = db.get(Project, "project-1")
        first = db.get(Shot, shot_ids[0])
        second = db.get(Shot, shot_ids[1])
        assert job.status == "done"
        assert job.progress == 1.0
        assert project.status == "done"
        assert first.analysis["subject"] == "updated-1"
        assert second.analysis["subject"] == "two"
        assert first.keyframe_path.endswith(f"shot_{shot_ids[0]:06d}.jpg")
    assert capacity.active_jobs() == 0


def test_timeline_background_failure_marks_job_and_project(timeline_env, monkeypatch):
    settings, testing_session, shot_ids = timeline_env

    with testing_session() as db:
        project = db.get(Project, "project-1")
        mutation = timeline.queue_reanalysis(db, project, shot_ids[0], settings)

    def fail_probe(_path, _settings):
        raise RuntimeError("probe exploded")

    monkeypatch.setattr(media, "probe", fail_probe)
    timeline.run_timeline_reanalysis("project-1", mutation.job_id, [shot_ids[0]])

    with testing_session() as db:
        job = db.get(Job, mutation.job_id)
        project = db.get(Project, "project-1")
        assert job.status == "failed"
        assert job.step == "failed"
        assert "probe exploded" in job.error
        assert project.status == "failed"
    assert capacity.active_jobs() == 0


def test_timeline_api_boundary_returns_queued_job(timeline_client, monkeypatch):
    client, testing_session, shot_ids = timeline_client
    launches: list[tuple] = []
    monkeypatch.setattr(timeline, "run_timeline_reanalysis", lambda *args: launches.append(args))

    response = client.patch(
        f"/api/projects/project-1/shots/{shot_ids[0]}/boundary",
        json={"boundary_s": 1.2},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["action"] == "boundary"
    assert payload["affected_shot_ids"] == shot_ids[:2]
    assert payload["prompt_projects_invalidated"] == 1
    assert launches == [("project-1", payload["job_id"], shot_ids[:2])]
    with testing_session() as db:
        assert db.get(Project, "project-1").status == "queued"
        assert db.get(Job, payload["job_id"]).step == "timeline_queued"


def test_timeline_api_split_merge_and_reanalyze(timeline_client, monkeypatch):
    client, testing_session, shot_ids = timeline_client
    monkeypatch.setattr(timeline, "run_timeline_reanalysis", lambda *_args: None)

    split = client.post(
        f"/api/projects/project-1/shots/{shot_ids[0]}/split",
        json={"split_at": 1.0},
    )
    assert split.status_code == 202
    assert split.json()["action"] == "split"

    with testing_session() as db:
        project = db.get(Project, "project-1")
        project.status = "done"
        for job in db.scalars(
            select(Job).where(Job.project_id == project.id, Job.status == "queued")
        ):
            job.status = "done"
        db.commit()

    merge = client.post(
        "/api/projects/project-1/shots/merge",
        json={"shot_ids": [shot_ids[2], shot_ids[1]]},
    )
    assert merge.status_code == 202
    assert merge.json()["action"] == "merge"

    with testing_session() as db:
        project = db.get(Project, "project-1")
        project.status = "done"
        for job in db.scalars(
            select(Job).where(Job.project_id == project.id, Job.status == "queued")
        ):
            job.status = "done"
        db.commit()

    reanalyze = client.post(
        f"/api/projects/project-1/shots/{shot_ids[0]}/reanalyze"
    )
    assert reanalyze.status_code == 202
    assert reanalyze.json()["affected_shot_ids"] == [shot_ids[0]]
    assert reanalyze.json()["action"] == "reanalyze"


def test_timeline_api_error_mapping(timeline_client, monkeypatch):
    client, testing_session, shot_ids = timeline_client

    missing = client.patch(
        "/api/projects/project-1/shots/999999/boundary",
        json={"boundary_s": 1.2},
    )
    assert missing.status_code == 404

    invalid = client.patch(
        f"/api/projects/project-1/shots/{shot_ids[0]}/boundary",
        json={"boundary_s": 0.2},
    )
    assert invalid.status_code == 422

    with testing_session() as db:
        db.get(Project, "project-1").status = "running"
        db.commit()
    conflict = client.patch(
        f"/api/projects/project-1/shots/{shot_ids[0]}/boundary",
        json={"boundary_s": 1.2},
    )
    assert conflict.status_code == 409

    with testing_session() as db:
        db.get(Project, "project-1").status = "done"
        db.commit()
    monkeypatch.setattr(timeline.capacity, "has_capacity", lambda _limit: False)
    full = client.post(f"/api/projects/project-1/shots/{shot_ids[0]}/reanalyze")
    assert full.status_code == 503


def test_project_payload_exposes_timeline_minimum(timeline_client):
    client, _, _ = timeline_client
    response = client.get("/api/projects/project-1")
    assert response.status_code == 200
    assert response.json()["timeline_min_shot_seconds"] == 0.8
