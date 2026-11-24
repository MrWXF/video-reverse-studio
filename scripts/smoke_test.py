"""End-to-end smoke test: build a demo clip, run the mock pipeline, print result."""

import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import PROJECT_ROOT, get_settings
from app.db import SessionLocal, init_db
from app.models import Job, Project
from app.services import media, pipeline


def make_demo_video(target: Path) -> None:
    ffmpeg = media.resolve_ffmpeg(get_settings().ffmpeg_bin)
    if not ffmpeg:
        raise SystemExit("ffmpeg not found; install imageio-ffmpeg")
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=0x1c1917:s=640x360:d=2:r=25",
        "-f", "lavfi", "-i", "color=c=0x1d4ed8:s=640x360:d=2:r=25",
        "-f", "lavfi", "-i", "color=c=0x15803d:s=640x360:d=2:r=25",
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
        "-map", "[v]", "-pix_fmt", "yuv420p", str(target),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    settings = get_settings()
    init_db()
    demo = PROJECT_ROOT / "data" / "samples" / "demo.mp4"
    make_demo_video(demo)

    project_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    root = settings.data_dir / "projects" / project_id
    root.mkdir(parents=True, exist_ok=True)
    target = root / "source.mp4"
    target.write_bytes(demo.read_bytes())

    with SessionLocal() as db:
        db.add(Project(id=project_id, title="Smoke Demo", source_path=str(target), status="queued"))
        db.add(Job(id=job_id, project_id=project_id, status="queued", step="queued"))
        db.commit()

    pipeline.run_pipeline(project_id, job_id)

    with SessionLocal() as db:
        project = db.get(Project, project_id)
        job = db.get(Job, job_id)
        assert project is not None and job is not None
        print("project_status:", project.status)
        print("shots:", len(project.shots))
        print("job:", job.status, job.step, job.progress, job.metrics)
        if job.error:
            print("error:", job.error)

    recipe = root / "output" / "video.md"
    print("recipe_exists:", recipe.exists())
    if recipe.exists():
        print("recipe_bytes:", recipe.stat().st_size)
        print("---- head ----")
        print(recipe.read_text(encoding="utf-8")[:700])


if __name__ == "__main__":
    main()