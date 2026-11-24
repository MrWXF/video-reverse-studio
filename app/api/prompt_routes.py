import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import PromptProject
from ..schemas import PromptBrief, PromptPlan
from ..serializers import prompt_project_payload
from ..services import prompt_export, prompt_generation

router = APIRouter()


def _get_project(db: Session, project_id: str) -> PromptProject:
    project = db.get(PromptProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="提示词项目不存在")
    return project


@router.post("/api/prompt-projects", status_code=201)
def create_prompt_project(
    brief: PromptBrief,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    project = PromptProject(
        id=str(uuid.uuid4()),
        title=brief.title.strip() or brief.idea[:60],
        brief_json=brief.model_dump(mode="json"),
        status="queued",
        step="queued",
    )
    db.add(project)
    db.commit()
    background.add_task(prompt_generation.run_prompt_generation, project.id)
    return {"prompt_project_id": project.id, "status": "queued"}


@router.get("/api/prompt-projects")
def list_prompt_projects(db: Session = Depends(get_db)) -> list[dict]:
    projects = db.scalars(
        select(PromptProject).order_by(PromptProject.created_at.desc())
    ).all()
    return [prompt_project_payload(project) for project in projects]


@router.get("/api/prompt-projects/{project_id}")
def get_prompt_project(project_id: str, db: Session = Depends(get_db)) -> dict:
    return prompt_project_payload(_get_project(db, project_id), include_plan=True)


@router.post("/api/prompt-projects/{project_id}/regenerate", status_code=202)
def regenerate_prompt_project(
    project_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    project = _get_project(db, project_id)
    if project.status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="该提示词项目正在生成")

    project.status = "queued"
    project.step = "queued"
    project.progress = 0.0
    project.error = ""
    project.plan_json = {}
    db.commit()
    background.add_task(prompt_generation.run_prompt_generation, project.id)
    return {"prompt_project_id": project.id, "status": "queued"}


@router.get("/api/prompt-projects/{project_id}/export")
def export_prompt_project(
    project_id: str,
    format: str = "md",
    db: Session = Depends(get_db),
):
    project = _get_project(db, project_id)
    if project.status != "done" or not project.plan_json:
        raise HTTPException(status_code=404, detail="提示词方案尚未生成")

    plan = PromptPlan.model_validate(project.plan_json)
    filename = f"{project.id}.md"
    if format.lower() == "json":
        return JSONResponse(
            content=json.loads(prompt_export.render_prompt_json(plan)),
            headers={"Content-Disposition": f'attachment; filename="{filename[:-3]}.json"'},
        )

    return PlainTextResponse(
        prompt_export.render_prompt_markdown(plan),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/api/prompt-projects/{project_id}")
def delete_prompt_project(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = _get_project(db, project_id)
    db.delete(project)
    db.commit()
    return {"deleted": project_id}
