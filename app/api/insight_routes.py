"""Phase 1 insight APIs: spend summaries, shot templates, and edit audit."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import Settings, get_settings
from ..db import get_db
from ..models import Job, Project, PromptProject, Shot, ShotEditEvent, ShotTemplate
from ..schemas import PromptPlan, ShotTemplateApply, ShotTemplateSave
from ..serializers import prompt_project_payload
from ..services import cost, prompt_versions
from ..services import shot_templates as template_service

router = APIRouter()


def _prompt_plan(project: PromptProject) -> PromptPlan:
    if project.status != "done" or not project.plan_json:
        raise HTTPException(status_code=409, detail="提示词方案尚未生成完成")
    try:
        return PromptPlan.model_validate(project.plan_json)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="提示词方案数据损坏") from exc


@router.get("/api/projects/{project_id}/cost")
def project_cost(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    job = db.scalar(
        select(Job)
        .where(Job.project_id == project_id)
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    metrics = (job.metrics if job else {}) or {}
    settings: Settings = get_settings()
    return {
        "project_id": project_id,
        "job_id": job.id if job else None,
        "metrics": metrics,
        "cost": cost.estimate_usage(metrics, settings),
    }


@router.get("/api/prompt-projects/{project_id}/cost")
def prompt_project_cost(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = db.get(PromptProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="提示词项目不存在")
    metrics = project.metrics or {}
    settings: Settings = get_settings()
    return {
        "project_id": project_id,
        "metrics": metrics,
        "cost": cost.estimate_usage(metrics, settings),
    }


@router.get("/api/projects/{project_id}/edit-events")
def list_edit_events(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict]:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    events = db.scalars(
        select(ShotEditEvent)
        .where(ShotEditEvent.project_id == project_id)
        .order_by(ShotEditEvent.created_at.desc(), ShotEditEvent.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": event.id,
            "shot_id": event.shot_id,
            "shot_index": event.shot_index,
            "source": event.source,
            "changes": event.changes or {},
            "created_at": event.created_at.isoformat()
            if event.created_at
            else None,
        }
        for event in events
    ]


@router.post(
    "/api/projects/{project_id}/shots/{shot_id}/save-template",
    status_code=201,
)
def save_shot_template(
    project_id: str,
    shot_id: int,
    payload: ShotTemplateSave,
    db: Session = Depends(get_db),
) -> dict:
    shot = db.scalar(
        select(Shot).where(
            Shot.id == shot_id,
            Shot.project_id == project_id,
        )
    )
    if shot is None:
        raise HTTPException(status_code=404, detail="镜头不存在")
    template = template_service.template_from_shot(shot, payload)
    db.add(template)
    db.commit()
    db.refresh(template)
    return template_service.template_payload(template)


@router.get("/api/shot-templates")
def list_shot_templates(
    search: str = "",
    category: str = "",
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict]:
    templates = db.scalars(
        select(ShotTemplate).order_by(ShotTemplate.created_at.desc()).limit(limit * 4)
    ).all()
    query = search.strip().casefold()
    selected_category = category.strip().casefold()
    result: list[dict] = []
    for template in templates:
        if selected_category and template.category.casefold() != selected_category:
            continue
        if query:
            haystack = " ".join(
                [
                    template.name,
                    template.description,
                    template.category,
                    template.shot_type,
                    template.camera_movement,
                    template.lighting,
                    template.visual_style,
                    " ".join(template.tags or []),
                ]
            ).casefold()
            if query not in haystack:
                continue
        result.append(template_service.template_payload(template))
        if len(result) >= limit:
            break
    return result


@router.delete("/api/shot-templates/{template_id}")
def delete_shot_template(template_id: int, db: Session = Depends(get_db)) -> dict:
    template = db.get(ShotTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    db.delete(template)
    db.commit()
    return {"deleted": template_id}


@router.post("/api/prompt-projects/{project_id}/apply-template")
def apply_shot_template(
    project_id: str,
    payload: ShotTemplateApply,
    db: Session = Depends(get_db),
) -> dict:
    project = db.scalar(
        select(PromptProject)
        .options(selectinload(PromptProject.versions))
        .where(PromptProject.id == project_id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="提示词项目不存在")
    plan = _prompt_plan(project)
    template = db.get(ShotTemplate, payload.template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    warnings = template_service.apply_template(plan, template, payload)
    plan.warnings = list(dict.fromkeys([*(plan.warnings or []), *warnings]))
    project.plan_json = plan.model_dump(mode="json")
    prompt_versions.create_prompt_version(db, project, "template_apply")
    db.commit()
    db.refresh(project)
    return prompt_project_payload(project, include_plan=True)
