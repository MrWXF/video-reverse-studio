import copy
import json
import secrets
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..db import get_db
from ..models import DeliveryReview, Project, PromptProject, PromptShare, PromptVersion
from ..schemas import EntityBible, PromptBrief, PromptPlan, PromptShotUpdate, ShareCreate
from ..serializers import (
    prompt_project_payload,
    review_payload,
    share_payload,
)
from ..services import (
    comparison,
    delivery_review,
    delivery_zip,
    model_profiles,
    prompt_export,
    prompt_generation,
    prompt_versions,
    sse,
)
from ..services.reference import build_reference_context

router = APIRouter()
REVIEW_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}


def _get_project(db: Session, project_id: str) -> PromptProject:
    project = db.get(PromptProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="提示词项目不存在")
    return project


def _get_done_plan(project: PromptProject) -> PromptPlan:
    if project.status != "done" or not project.plan_json:
        raise HTTPException(status_code=409, detail="提示词方案尚未生成完成")
    try:
        return PromptPlan.model_validate(project.plan_json)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="提示词方案数据损坏") from exc


@router.post("/api/prompt-projects", status_code=201)
def create_prompt_project(
    brief: PromptBrief,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    reference = None
    if brief.reference_project_id:
        source = db.scalar(
            select(Project)
            .options(selectinload(Project.shots))
            .where(Project.id == brief.reference_project_id)
        )
        if source is None:
            raise HTTPException(status_code=404, detail="参考项目不存在")
        if source.status != "done" or not source.shots:
            raise HTTPException(status_code=409, detail="参考项目尚未完成分析")
        reference = build_reference_context(source, brief.reference_mode)

    project = PromptProject(
        id=str(uuid.uuid4()),
        title=brief.title.strip() or brief.idea[:60],
        source_project_id=brief.reference_project_id,
        reference_mode=brief.reference_mode,
        reference_snapshot_json=reference.model_dump(mode="json") if reference else {},
        entity_bible_json=brief.entity_bible.model_dump(mode="json"),
        brief_json=brief.model_dump(mode="json"),
        status="queued",
        step="queued",
    )
    db.add(project)
    db.commit()
    background.add_task(prompt_generation.run_prompt_generation, project.id)
    return {"prompt_project_id": project.id, "status": "queued"}


@router.patch("/api/prompt-projects/{project_id}/shots/{shot_index}")
def update_prompt_shot(
    project_id: str,
    shot_index: int,
    update: PromptShotUpdate,
    db: Session = Depends(get_db),
) -> dict:
    project = _get_project(db, project_id)
    plan = _get_done_plan(project)
    shot = next((item for item in plan.shots if item.index == shot_index), None)
    if shot is None:
        raise HTTPException(status_code=404, detail="镜头不存在")

    changes = update.model_dump(exclude_unset=True)
    locked_fields = changes.pop("locked_fields", None)
    for field, value in changes.items():
        setattr(shot, field, value)
    if locked_fields is not None:
        shot.locked_fields = prompt_generation._clean_locked_fields(locked_fields)
    project.plan_json = plan.model_dump(mode="json")
    prompt_versions.create_prompt_version(db, project, "shot_edit")
    db.commit()
    return prompt_project_payload(project, include_plan=True)


@router.post("/api/prompt-projects/{project_id}/shots/{shot_index}/regenerate")
def regenerate_prompt_shot(
    project_id: str,
    shot_index: int,
    db: Session = Depends(get_db),
) -> dict:
    project = _get_project(db, project_id)
    _get_done_plan(project)
    try:
        plan, metrics = prompt_generation.regenerate_prompt_shot(
            project, shot_index, get_settings()
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    project.plan_json = plan.model_dump(mode="json")
    project.metrics = metrics
    prompt_versions.create_prompt_version(db, project, "shot_regenerate")
    db.commit()
    return prompt_project_payload(project, include_plan=True)


@router.get("/api/prompt-projects/{project_id}/versions")
def list_prompt_versions(project_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _get_project(db, project_id)
    versions = db.scalars(
        select(PromptVersion)
        .where(PromptVersion.prompt_project_id == project_id)
        .order_by(PromptVersion.version.desc())
    ).all()
    return [prompt_versions.version_payload(version) for version in versions]


@router.get("/api/prompt-projects/{project_id}/versions/{version_id}")
def get_prompt_version(
    project_id: str,
    version_id: str,
    db: Session = Depends(get_db),
) -> dict:
    version = db.get(PromptVersion, version_id)
    if version is None or version.prompt_project_id != project_id:
        raise HTTPException(status_code=404, detail="版本不存在")
    return prompt_versions.version_payload(version, include_plan=True)


@router.post("/api/prompt-projects/{project_id}/versions/{version_id}/restore")
def restore_prompt_version(
    project_id: str,
    version_id: str,
    db: Session = Depends(get_db),
) -> dict:
    project = _get_project(db, project_id)
    version = db.get(PromptVersion, version_id)
    if version is None or version.prompt_project_id != project_id:
        raise HTTPException(status_code=404, detail="版本不存在")
    try:
        PromptPlan.model_validate(version.plan_json or {})
        PromptBrief.model_validate(version.brief_json or {})
    except Exception as exc:
        raise HTTPException(status_code=409, detail="版本快照无法恢复") from exc

    project.title = version.title or project.title
    project.plan_json = copy.deepcopy(version.plan_json or {})
    project.brief_json = copy.deepcopy(version.brief_json or {})
    project.entity_bible_json = copy.deepcopy(version.entity_bible_json or {})
    project.status = "done"
    project.step = "done"
    project.progress = 1.0
    project.error = ""
    prompt_versions.create_prompt_version(db, project, "restore")
    db.commit()
    return prompt_project_payload(project, include_plan=True)


@router.get("/api/prompt-projects/{project_id}/entity-bible")
def get_entity_bible(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = _get_project(db, project_id)
    return {"entity_bible": project.entity_bible_json or {}}


@router.patch("/api/prompt-projects/{project_id}/entity-bible")
def update_entity_bible(
    project_id: str,
    bible: EntityBible,
    db: Session = Depends(get_db),
) -> dict:
    project = _get_project(db, project_id)
    data = bible.model_dump(mode="json")
    project.entity_bible_json = data
    brief = dict(project.brief_json or {})
    brief["entity_bible"] = data
    project.brief_json = brief
    if project.plan_json:
        prompt_versions.create_prompt_version(db, project, "entity_edit")
    db.commit()
    return prompt_project_payload(project, include_plan=True)


@router.get("/api/prompt-projects/{project_id}/comparison")
def get_prompt_comparison(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = _get_project(db, project_id)
    plan = _get_done_plan(project)
    if not project.reference_snapshot_json:
        raise HTTPException(status_code=409, detail="该方案没有参考项目")
    return comparison.build_reference_comparison(
        project.reference_snapshot_json,
        project.reference_mode or "style",
        plan,
    )


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


@router.post("/api/prompt-projects/{project_id}/cancel", status_code=202)
def cancel_prompt_project(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = _get_project(db, project_id)
    if project.status not in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="该任务当前不可取消")
    project.status = "cancelled"
    project.step = "cancelled"
    project.error = "用户已取消生成"
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"prompt_project_id": project.id, "status": "cancelled"}


@router.get("/api/prompt-projects/{project_id}/events")
def prompt_project_events(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _get_project(db, project_id)
    return StreamingResponse(
        sse.prompt_event_stream(request, project_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/model-profiles")
def list_model_profiles() -> list[dict]:
    return model_profiles.model_profile_options()


@router.post("/api/prompt-projects/{project_id}/reviews", status_code=202)
def create_delivery_review(
    project_id: str,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    project = _get_project(db, project_id)
    _get_done_plan(project)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in REVIEW_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"不支持的视频格式：{suffix or '未知'}")
    settings = get_settings()
    review_id = str(uuid.uuid4())
    root = settings.data_dir / "reviews" / review_id
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"delivery{suffix}"
    limit = settings.max_upload_mb * 1024 * 1024
    written = 0
    try:
        with target.open("wb") as handle:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件超过 {settings.max_upload_mb}MB 限制",
                    )
                handle.write(chunk)
        if written == 0:
            raise HTTPException(status_code=400, detail="上传的文件为空")
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise

    review = DeliveryReview(
        id=review_id,
        prompt_project_id=project.id,
        filename=file.filename or target.name,
        source_path=str(target),
        status="queued",
        step="queued",
    )
    db.add(review)
    db.commit()
    background.add_task(delivery_review.run_delivery_review, review.id)
    return review_payload(review)


@router.get("/api/prompt-projects/{project_id}/reviews")
def list_delivery_reviews(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[dict]:
    _get_project(db, project_id)
    reviews = db.scalars(
        select(DeliveryReview)
        .where(DeliveryReview.prompt_project_id == project_id)
        .order_by(DeliveryReview.created_at.desc())
    ).all()
    return [review_payload(review) for review in reviews]


@router.get("/api/prompt-projects/{project_id}/reviews/{review_id}")
def get_delivery_review(
    project_id: str,
    review_id: str,
    db: Session = Depends(get_db),
) -> dict:
    review = db.get(DeliveryReview, review_id)
    if review is None or review.prompt_project_id != project_id:
        raise HTTPException(status_code=404, detail="回测记录不存在")
    return review_payload(review, include_result=True)


@router.delete("/api/prompt-projects/{project_id}/reviews/{review_id}")
def delete_delivery_review(
    project_id: str,
    review_id: str,
    db: Session = Depends(get_db),
) -> dict:
    review = db.get(DeliveryReview, review_id)
    if review is None or review.prompt_project_id != project_id:
        raise HTTPException(status_code=404, detail="回测记录不存在")
    db.delete(review)
    db.commit()
    root = (get_settings().data_dir / "reviews" / review_id).resolve()
    reviews_root = (get_settings().data_dir / "reviews").resolve()
    if root.exists() and reviews_root in root.parents:
        shutil.rmtree(root, ignore_errors=True)
    return {"deleted": review_id}


@router.get("/api/prompt-projects/{project_id}/export/zip")
def export_prompt_zip(project_id: str, db: Session = Depends(get_db)) -> Response:
    project = _get_project(db, project_id)
    plan = _get_done_plan(project)
    versions = db.scalars(
        select(PromptVersion)
        .where(PromptVersion.prompt_project_id == project.id)
        .order_by(PromptVersion.version)
    ).all()
    source_project = None
    if project.source_project_id:
        source_project = db.scalar(
            select(Project)
            .options(selectinload(Project.shots))
            .where(Project.id == project.source_project_id)
        )
    content = delivery_zip.build_prompt_zip(
        project,
        plan,
        list(versions),
        get_settings(),
        source_project=source_project,
    )
    filename = f"prompt-{project.id}.zip"
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/api/prompt-projects/{project_id}/shares", status_code=201)
def create_prompt_share(
    project_id: str,
    payload: ShareCreate,
    db: Session = Depends(get_db),
) -> dict:
    project = _get_project(db, project_id)
    _get_done_plan(project)
    version_number = None
    if payload.version_id:
        version = db.get(PromptVersion, payload.version_id)
        if version is None or version.prompt_project_id != project.id:
            raise HTTPException(status_code=404, detail="分享版本不存在")
        version_number = version.version
    expires_at = None
    if payload.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)
    share = PromptShare(
        id=str(uuid.uuid4()),
        prompt_project_id=project.id,
        version_id=payload.version_id,
        token=secrets.token_urlsafe(24),
        permission=payload.permission,
        expires_at=expires_at,
    )
    db.add(share)
    db.commit()
    return share_payload(share, version_number=version_number)


@router.get("/api/prompt-projects/{project_id}/shares")
def list_prompt_shares(project_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _get_project(db, project_id)
    shares = db.scalars(
        select(PromptShare)
        .where(PromptShare.prompt_project_id == project_id)
        .order_by(PromptShare.created_at.desc())
    ).all()
    versions = {
        version.id: version.version
        for version in db.scalars(
            select(PromptVersion).where(PromptVersion.prompt_project_id == project_id)
        ).all()
    }
    return [
        share_payload(share, version_number=versions.get(share.version_id or ""))
        for share in shares
    ]


@router.delete("/api/prompt-projects/{project_id}/shares/{share_id}")
def revoke_prompt_share(
    project_id: str,
    share_id: str,
    db: Session = Depends(get_db),
) -> dict:
    share = db.get(PromptShare, share_id)
    if share is None or share.prompt_project_id != project_id:
        raise HTTPException(status_code=404, detail="分享链接不存在")
    share.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return {"revoked": share_id}


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
