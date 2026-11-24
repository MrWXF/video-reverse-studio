from .models import Job, Project, PromptProject, Shot


def shot_payload(shot: Shot) -> dict:
    keyframe_url = (
        f"/api/projects/{shot.project_id}/shots/{shot.id}/keyframe"
        if shot.keyframe_path
        else ""
    )
    return {
        "id": shot.id,
        "index": shot.index,
        "start_s": shot.start_s,
        "end_s": shot.end_s,
        "keyframe_url": keyframe_url,
        "transcript": shot.transcript,
        "origin": shot.origin,
        "confidence": shot.confidence,
        "analysis": shot.analysis or {},
    }


def job_payload(job: Job | None) -> dict | None:
    if job is None:
        return None
    return {
        "id": job.id,
        "status": job.status,
        "step": job.step,
        "progress": job.progress,
        "error": job.error,
        "metrics": job.metrics or {},
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def project_payload(
    project: Project,
    job: Job | None = None,
    include_shots: bool = False,
) -> dict:
    payload = {
        "id": project.id,
        "title": project.title,
        "status": project.status,
        "duration": project.duration,
        "width": project.width,
        "height": project.height,
        "fps": project.fps,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "video_url": f"/api/projects/{project.id}/video",
        "recipe_url": f"/api/projects/{project.id}/recipe",
        "job": job_payload(job),
    }
    if include_shots:
        payload["shots"] = [shot_payload(shot) for shot in project.shots]
    return payload


def prompt_project_payload(
    project: PromptProject,
    include_plan: bool = False,
) -> dict:
    brief = project.brief_json or {}
    plan = project.plan_json or {}
    payload = {
        "id": project.id,
        "title": project.title,
        "status": project.status,
        "step": project.step,
        "progress": project.progress,
        "error": project.error,
        "metrics": project.metrics or {},
        "target_model": brief.get("target_model", ""),
        "shot_count": len(plan.get("shots") or []),
        "brief": brief,
        "export_url": f"/api/prompt-projects/{project.id}/export",
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }
    if include_plan:
        payload["plan"] = plan
    return payload
