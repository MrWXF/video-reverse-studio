from app.models import Project, Shot
from app.serializers import project_payload, shot_payload


def test_project_and_shot_payloads_use_scoped_media_urls():
    project = Project(
        id="project-1",
        title="测试项目",
        source_path="/tmp/source.mp4",
        status="done",
    )
    shot = Shot(
        id=7,
        project_id="project-1",
        index=1,
        start_s=0.0,
        end_s=1.0,
        keyframe_path="projects/project-1/frames/shot_0001.jpg",
    )

    assert project_payload(project)["video_url"] == "/api/projects/project-1/video"
    assert shot_payload(shot)["keyframe_url"] == (
        "/api/projects/project-1/shots/7/keyframe"
    )
