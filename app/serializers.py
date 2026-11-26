from .models import (
    DeliveryReview,
    GenerationJob,
    Job,
    Project,
    PromptComment,
    PromptProject,
    PromptShare,
    Shot,
)


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
    timeline_min_shot_seconds: float | None = None,
) -> dict:
    payload = {
        "id": project.id,
        "title": project.title,
        "status": project.status,
        "duration": project.duration,
        "width": project.width,
        "height": project.height,
        "fps": project.fps,
        "timeline_min_shot_seconds": timeline_min_shot_seconds,
        "shot_count": len(project.shots) if project.shots else 0,
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
    snapshot = project.reference_snapshot_json or {}
    reference_recipe = snapshot.get("recipe") or {}
    reference_shots = reference_recipe.get("shots") or []
    reference = None
    if project.source_project_id and snapshot:
        reference = {
            "project_id": project.source_project_id,
            "project_url": f"/api/projects/{project.source_project_id}",
            "mode": project.reference_mode or snapshot.get("mode") or "style",
            "title": reference_recipe.get("title", ""),
            "shot_count": len(reference_shots),
            "pacing": reference_recipe.get("pacing", ""),
            "summary": reference_recipe.get("summary", ""),
            "palette": [
                color
                for shot in reference_shots
                for color in (shot.get("color_palette") or [])
            ][:8],
        }
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
        "entity_bible": project.entity_bible_json or {},
        "version_count": len(project.versions),
        "source_project_id": project.source_project_id,
        "reference_mode": project.reference_mode or "style",
        "reference": reference,
        "export_url": f"/api/prompt-projects/{project.id}/export",
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }
    if include_plan:
        payload["plan"] = plan
        if reference is not None:
            reference["recipe"] = reference_recipe
    return payload


def generation_job_payload(job: GenerationJob) -> dict:
    result = job.result_json or {}
    shots: list[dict] = []
    for stored in result.get("shots") or []:
        item = dict(stored)
        filename = item.pop("filename", "")
        if item.get("status") == "succeeded" and filename:
            item["download_url"] = (
                f"/api/generation-jobs/{job.id}/shots/{item.get('shot_index')}/video"
            )
        else:
            item["download_url"] = ""
        shots.append(item)
    request_data = job.request_json or {}
    return {
        "id": job.id,
        "prompt_project_id": job.prompt_project_id,
        "provider": job.provider,
        "model": job.model,
        "status": job.status,
        "step": job.step,
        "progress": job.progress,
        "error": job.error,
        "request": request_data,
        "shot_indices": request_data.get("shot_indices") or [],
        "shot_count": len(request_data.get("shot_indices") or []),
        "result": {"provider": result.get("provider", job.provider), "shots": shots},
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def review_payload(review: DeliveryReview, include_result: bool = False) -> dict:
    payload = {
        "id": review.id,
        "filename": review.filename,
        "status": review.status,
        "step": review.step,
        "progress": review.progress,
        "error": review.error,
        "created_at": review.created_at.isoformat() if review.created_at else None,
        "updated_at": review.updated_at.isoformat() if review.updated_at else None,
    }
    if include_result:
        payload["result"] = review.result_json or {}
    return payload


def share_payload(share: PromptShare, version_number: int | None = None) -> dict:
    return {
        "id": share.id,
        "token": share.token,
        "url": f"/share/{share.token}",
        "permission": share.permission,
        "version_id": share.version_id,
        "version_number": version_number,
        "expires_at": share.expires_at.isoformat() if share.expires_at else None,
        "revoked_at": share.revoked_at.isoformat() if share.revoked_at else None,
        "created_at": share.created_at.isoformat() if share.created_at else None,
    }


def comment_payload(comment: PromptComment) -> dict:
    return {
        "id": comment.id,
        "author": comment.author,
        "content": comment.content,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }
