import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import SessionLocal
from ..models import PromptProject
from ..observability import request_id_ctx
from ..prompts import load_catalog, load_prompt
from ..schemas import PromptBrief, PromptPlan, PromptShot, ReferenceContext
from . import capacity
from .llm import LLMGateway
from .mock import MockScenarioError
from .model_profiles import get_model_profile, validate_prompt_plan
from .prompt_versions import create_prompt_version
from .redaction import redact_exception
from .reference import compact_reference
from .retry import RetryableServiceError, is_retryable_exception, retry_call

logger = logging.getLogger(__name__)

_LOCKABLE_FIELDS = {
    "shot_type",
    "camera_movement",
    "subject",
    "action",
    "scene",
    "lighting",
    "color_palette",
    "prompt",
    "negative_prompt",
    "transition",
    "remake_notes",
}


def _update_project(
    db: Session,
    project: PromptProject,
    *,
    status: str | None = None,
    step: str | None = None,
    progress: float | None = None,
    error: str | None = None,
) -> None:
    if status is not None:
        project.status = status
    if step is not None:
        project.step = step
    if progress is not None:
        project.progress = max(0.0, min(1.0, progress))
    if error is not None:
        project.error = error
    project.updated_at = datetime.now(timezone.utc)
    db.commit()


def run_prompt_generation(project_id: str, request_id: str | None = None) -> None:
    """Generate and persist a prompt plan with bounded concurrency and retries."""
    settings = get_settings()
    trace_id = request_id or f"prompt-{project_id}"
    token = request_id_ctx.set(trace_id)
    try:
        with SessionLocal() as db:
            project = db.get(PromptProject, project_id)
            if project is None:
                logger.error("prompt project missing: %s", project_id)
                return
            if not capacity.acquire_job(settings.max_active_jobs):
                project.status = "failed"
                project.step = "failed"
                project.error = "系统繁忙，当前同时生成任务已达上限，请稍后重试"
                project.updated_at = datetime.now(timezone.utc)
                db.commit()
                return
            try:
                db.refresh(project)
                if project.status == "cancelled":
                    return
                brief = PromptBrief.model_validate(project.brief_json or {})
                reference = (
                    ReferenceContext.model_validate(project.reference_snapshot_json)
                    if project.reference_snapshot_json
                    else None
                )
                _update_project(db, project, status="running", step="planning", progress=0.15)
                gateway = LLMGateway(settings)

                def generate_attempt() -> tuple[PromptPlan, list[str]]:
                    candidate, attempt_notes = generate_prompt_plan(
                        brief, gateway, reference
                    )
                    _update_project(db, project, step="validating", progress=0.85)
                    candidate = normalize_prompt_plan(
                        candidate,
                        brief,
                        reference=reference,
                        catalog_path=settings.prompt_catalog_file,
                    )
                    return candidate, attempt_notes

                def on_retry(attempt: int, exc: BaseException, delay: float) -> None:
                    db.rollback()
                    logger.warning(
                        "retrying prompt generation project=%s attempt=%s delay=%.2fs",
                        project_id,
                        attempt,
                        delay,
                    )
                    project.step = "retrying"
                    project.progress = 0.1
                    project.error = redact_exception(exc, settings, limit=500)
                    project.updated_at = datetime.now(timezone.utc)
                    db.commit()

                plan, notes = retry_call(
                    generate_attempt,
                    attempts=settings.retry_max_attempts,
                    base_delay=settings.retry_base_delay_s,
                    max_delay=settings.retry_max_delay_s,
                    on_retry=on_retry,
                )
                plan.warnings.extend(notes)

                db.refresh(project)
                if project.status == "cancelled":
                    return

                project.title = plan.title or project.title
                project.plan_json = plan.model_dump(mode="json")
                project.metrics = {**gateway.stats(), "request_id": trace_id}
                create_prompt_version(db, project, "generate")
                _update_project(
                    db,
                    project,
                    status="done",
                    step="done",
                    progress=1.0,
                    error="",
                )
            except Exception as exc:
                logger.exception("prompt generation failed for project %s", project_id)
                db.rollback()
                project.status = "failed"
                project.step = "failed"
                project.error = redact_exception(exc, settings)
                project.updated_at = datetime.now(timezone.utc)
                db.commit()
            finally:
                capacity.release_job()
    finally:
        request_id_ctx.reset(token)


def generate_prompt_plan(
    brief: PromptBrief,
    gateway: LLMGateway,
    reference: ReferenceContext | None = None,
) -> tuple[PromptPlan, list[str]]:
    if not gateway.enabled:
        return mock_prompt_plan(
            brief,
            reference,
            scenario=gateway.settings.mock_scenario,
            catalog_path=gateway.settings.prompt_catalog_file,
        ), ["Mock 模式：未调用文本模型"]

    llm = gateway.chat_model()
    if llm is None:
        return mock_prompt_plan(
            brief,
            reference,
            scenario=gateway.settings.mock_scenario,
            catalog_path=gateway.settings.prompt_catalog_file,
        ), ["未配置文本模型，已使用 Mock 方案"]

    messages = [
        SystemMessage(content=load_prompt("video_prompt_generation")),
        HumanMessage(content=_brief_text(brief, reference)),
    ]

    try:
        structured = llm.with_structured_output(PromptPlan, include_raw=True)
        result = structured.invoke(messages)
        raw = result.get("raw") if isinstance(result, dict) else None
        parsed = result.get("parsed") if isinstance(result, dict) else None
        if raw is not None:
            gateway.record_usage(raw)
        if parsed is not None:
            return parsed, ["结构化模型输出"]
        raise ValueError("结构化输出解析失败")
    except Exception as exc:
        logger.warning("structured prompt plan failed: %s", exc)

    try:
        chain = llm | JsonOutputParser()
        data = chain.invoke(messages)
        return PromptPlan.model_validate(data), ["结构化输出失败，已使用 JSON 解析降级"]
    except Exception as exc:
        logger.error("prompt plan generation failed: %s", exc)
        if is_retryable_exception(exc):
            raise RetryableServiceError(
                redact_exception(exc, gateway.settings, limit=500)
            ) from exc
        raise RuntimeError(f"提示词生成失败：{str(exc)[:500]}") from exc


def _brief_text(brief: PromptBrief, reference: ReferenceContext | None = None) -> str:
    payload = json.dumps(brief.model_dump(mode="json"), ensure_ascii=False, indent=2)
    text = (
        "请根据以下创意简报生成视频提示词方案。"
        "严格按 schema 输出，不要输出 Markdown 代码块。\n\n"
        f"{payload}"
    )
    if reference is not None:
        reference_payload = json.dumps(
            compact_reference(reference), ensure_ascii=False, indent=2
        )
        text += (
            "\n\n以下是从参考项目提取的可迁移上下文。请严格按 reference_mode 继承：\n"
            "- style：只继承色调、光线、质感、景别与运镜偏好和节奏，不复制原主体与情节。\n"
            "- structure：继承镜头数量、时长结构、景别顺序与运镜，主体和场景必须根据新创意重写。\n"
            "- full：逐镜参考构图、光线和镜头语言，但替换主体、动作和场景，避免直接复制原片。\n"
            f"{reference_payload}"
        )
    return text


def normalize_prompt_plan(
    plan: PromptPlan,
    brief: PromptBrief,
    *,
    generated_at: datetime | None = None,
    reference: ReferenceContext | None = None,
    catalog_path: str = "",
) -> PromptPlan:
    """Normalize model output into a complete, time-aligned prompt plan."""
    catalog = load_catalog(catalog_path)
    shots = sorted(plan.shots, key=lambda item: item.index)
    if not shots:
        raise RuntimeError("模型未返回任何镜头")

    warnings = list(plan.warnings)
    global_style = (
        plan.global_style.strip()
        or brief.style
        or _reference_style(reference)
        or "cinematic natural style"
    )
    if len(shots) > brief.shot_count:
        shots = shots[: brief.shot_count]
        warnings.append(f"镜头数超过目标，已截断为 {brief.shot_count} 个")
    if len(shots) != brief.shot_count:
        warnings.append(
            f"目标为 {brief.shot_count} 个镜头，模型返回 {len(shots)} 个"
        )

    durations = []
    fallback_duration = brief.duration_s / len(shots)
    for shot in shots:
        duration = shot.duration or (shot.end_s - shot.start_s)
        durations.append(max(0.1, duration or fallback_duration))

    total = sum(durations)
    scale = brief.duration_s / total if total > 0 else 1.0
    cursor = 0.0
    normalized_shots: list[PromptShot] = []

    for index, (shot, raw_duration) in enumerate(
        zip(shots, durations, strict=False), start=1
    ):
        duration = round(raw_duration * scale, 3)
        if index == len(shots):
            duration = round(brief.duration_s - cursor, 3)
        duration = max(0.1, duration)
        shot.index = index
        shot.start_s = round(cursor, 3)
        shot.end_s = round(cursor + duration, 3)
        shot.duration = duration
        cursor = shot.end_s
        shot.prompt = shot.prompt.strip() or _compose_prompt(shot, brief, global_style)
        shot.negative_prompt = shot.negative_prompt or brief.negative_prompt
        shot.shot_type = shot.shot_type or "中景"
        shot.camera_movement = shot.camera_movement or "固定"
        shot.transition = shot.transition or catalog["transitions"][
            (index - 1) % len(catalog["transitions"])
        ]
        shot.locked_fields = _clean_locked_fields(shot.locked_fields)
        if reference is not None and reference.mode in {"structure", "full"}:
            source_shots = reference.recipe.shots
            if source_shots and not shot.source_shot_index:
                shot.source_shot_index = source_shots[(index - 1) % len(source_shots)].index
        normalized_shots.append(shot)

    plan.title = plan.title.strip() or brief.title.strip() or brief.idea[:40]
    plan.summary = plan.summary.strip() or (
        f"围绕“{brief.idea[:80]}”生成 {len(normalized_shots)} 个可执行镜头。"
    )
    plan.target_model = brief.target_model
    plan.language = brief.language
    plan.duration_s = brief.duration_s
    plan.aspect_ratio = brief.aspect_ratio
    plan.global_style = global_style
    plan.shots = normalized_shots
    plan.target_profile = get_model_profile(brief.target_model)
    plan.warnings = [*warnings, *validate_prompt_plan(plan, brief.duration_s)]
    plan.generated_at = generated_at or datetime.now(timezone.utc)
    return plan


def _compose_prompt(
    shot: PromptShot,
    brief: PromptBrief,
    global_style: str = "",
) -> str:
    subject = shot.subject or "the main subject"
    action = shot.action or "performs a clear, visually readable action"
    scene = shot.scene or "a clean cinematic environment"
    lighting = shot.lighting or "cinematic natural lighting"
    style = global_style or "commercial film look"
    mood = brief.mood or "clear and engaging"
    prompt = (
        f"{shot.shot_type} shot of {subject}, {action}, in {scene}, "
        f"{shot.camera_movement}, {lighting}, {style}, {mood} mood, "
        f"{brief.aspect_ratio} aspect ratio, optimized for {brief.target_model}, "
        "detailed texture, realistic motion, high production value"
    )
    rules = [rule for rule in brief.entity_bible.consistency_rules if rule][:3]
    if rules:
        prompt += ", continuity: " + "; ".join(rules)
    return prompt


def mock_prompt_plan(
    brief: PromptBrief,
    reference: ReferenceContext | None = None,
    *,
    scenario: str = "success",
    catalog_path: str = "",
) -> PromptPlan:
    scenario = (scenario or "success").lower().strip()
    if scenario == "fail":
        raise MockScenarioError("Mock 已按配置模拟提示词生成失败")
    if scenario == "slow":
        time.sleep(0.05)
    catalog = load_catalog(catalog_path)
    seed = int(hashlib.sha1(brief.idea.encode("utf-8")).hexdigest()[:8], 16)
    count = brief.shot_count
    step = brief.duration_s / count
    shots: list[PromptShot] = []
    reference_shots = reference.recipe.shots if reference else []
    reference_palette = [
        color
        for shot in reference_shots
        for color in shot.color_palette
    ]
    global_style = (
        brief.style or _reference_style(reference) or "cinematic natural style"
    )
    entity_subject = _entity_subject(brief)
    entity_scene = _entity_scene(brief)

    for index in range(1, count + 1):
        local = seed + index * 31
        shot_type = catalog["shot_types"][local % len(catalog["shot_types"])]
        movement = catalog["camera_moves"][
            (local // 3) % len(catalog["camera_moves"])
        ]
        lighting = catalog["lighting"][(local // 5) % len(catalog["lighting"])]
        transition = catalog["transitions"][
            (local // 7) % len(catalog["transitions"])
        ]
        palette = catalog["palettes"][(local // 11) % len(catalog["palettes"])]
        source_shot_index = None
        if reference_shots:
            source_shot = reference_shots[(index - 1) % len(reference_shots)]
            if reference.mode in {"structure", "full"}:
                shot_type = source_shot.shot_type
                movement = source_shot.camera_movement
                source_shot_index = source_shot.index
            if reference.mode in {"style", "full"}:
                lighting = source_shot.lighting or lighting
                palette = source_shot.color_palette or palette
            elif reference_palette:
                palette = reference_palette[:5]
        start_s = round((index - 1) * step, 3)
        end_s = round(index * step, 3)
        shot = PromptShot(
            index=index,
            start_s=start_s,
            end_s=end_s,
            duration=round(step, 3),
            shot_type=shot_type,
            camera_movement=movement,
            subject=entity_subject,
            action="a clear, purposeful action",
            scene=entity_scene,
            lighting=lighting,
            color_palette=palette,
            prompt="",
            negative_prompt=brief.negative_prompt,
            transition=transition,
            remake_notes="Mock 方案仅用于流程演示，配置文本模型后可生成真实创意。",
            source_shot_index=source_shot_index,
        )
        shot.prompt = _compose_prompt(shot, brief, global_style)
        shots.append(shot)

    return PromptPlan(
        title=brief.title or "未命名提示词方案",
        summary=f"为“{brief.idea[:80]}”生成 {count} 个镜头的 Mock 提示词方案。",
        target_model=brief.target_model,
        language=brief.language,
        duration_s=brief.duration_s,
        aspect_ratio=brief.aspect_ratio,
        global_style=global_style,
        target_profile=get_model_profile(brief.target_model),
        shots=shots,
        assumptions=["Mock 模式不调用模型，结果仅用于流程演示。"],
        warnings=["Mock 模式：未调用文本模型"],
    )


def _reference_style(reference: ReferenceContext | None) -> str:
    if reference is None:
        return ""
    return next(
        (shot.visual_style for shot in reference.recipe.shots if shot.visual_style),
        "",
    )


def _clean_locked_fields(fields: list[str] | None) -> list[str]:
    return list(dict.fromkeys(field for field in (fields or []) if field in _LOCKABLE_FIELDS))


def _entity_subject(brief: PromptBrief) -> str:
    bible = brief.entity_bible
    for item in [*bible.products, *bible.characters]:
        detail = item.appearance or item.description
        return f"{item.name}, {detail}" if detail else item.name
    return "the product or protagonist"


def _entity_scene(brief: PromptBrief) -> str:
    bible = brief.entity_bible
    if bible.scenes:
        item = bible.scenes[0]
        detail = item.appearance or item.description
        return f"{item.name}, {detail}" if detail else item.name
    return "a clean cinematic environment"


def _entity_context(brief: PromptBrief) -> str:
    payload = brief.entity_bible.model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, indent=2)


def regenerate_prompt_shot(
    project: PromptProject,
    shot_index: int,
    settings: Settings,
) -> tuple[PromptPlan, dict]:
    brief = PromptBrief.model_validate(project.brief_json or {})
    plan = PromptPlan.model_validate(project.plan_json or {})
    reference = (
        ReferenceContext.model_validate(project.reference_snapshot_json)
        if project.reference_snapshot_json
        else None
    )
    current = next(
        (shot for shot in plan.shots if shot.index == shot_index),
        None,
    )
    if current is None:
        raise ValueError("镜头不存在")

    locked = set(_clean_locked_fields(current.locked_fields))
    gateway = LLMGateway(settings)
    candidate = None
    notes: list[str] = []
    if gateway.enabled and "prompt" not in locked:
        candidate = _model_regenerate_shot(brief, current, gateway, reference)
        if candidate is not None:
            notes.append("单镜已由文本模型重生成")
    if candidate is None:
        candidate = _local_regenerate_shot(
            brief,
            current,
            locked,
            settings.prompt_catalog_file,
        )
        notes.append("单镜已局部重生成")

    merged = current.model_copy(deep=True)
    for field in _LOCKABLE_FIELDS - locked:
        if hasattr(candidate, field):
            setattr(merged, field, getattr(candidate, field))
    for field in locked:
        setattr(merged, field, getattr(current, field))
    merged.index = current.index
    merged.start_s = current.start_s
    merged.end_s = current.end_s
    merged.duration = current.duration
    merged.source_shot_index = current.source_shot_index
    merged.locked_fields = list(locked)
    if not merged.prompt.strip():
        merged.prompt = _compose_prompt(merged, brief, plan.global_style)

    plan.shots = [
        merged if shot.index == shot_index else shot for shot in plan.shots
    ]
    plan.warnings = list(dict.fromkeys([*plan.warnings, *notes]))
    plan.generated_at = datetime.now(timezone.utc)
    return plan, gateway.stats()


def _model_regenerate_shot(
    brief: PromptBrief,
    current: PromptShot,
    gateway: LLMGateway,
    reference: ReferenceContext | None,
) -> PromptShot | None:
    llm = gateway.chat_model()
    if llm is None:
        return None
    prompt = (
        "只重写下面这一个镜头，保持整体创意与镜头时间轴不变。"
        "返回完整 PromptShot 对象，不要修改 index、start_s、end_s、duration。\n\n"
        f"创意简报：\n{_brief_text(brief, reference)}\n\n"
        f"Entity Bible：\n{_entity_context(brief)}\n\n"
        f"当前镜头：\n{json.dumps(current.model_dump(mode='json'), ensure_ascii=False, indent=2)}"
    )
    try:
        structured = llm.with_structured_output(PromptShot, include_raw=True)
        result = retry_call(
            lambda: structured.invoke(
                [
                    SystemMessage(content=load_prompt("video_prompt_generation")),
                    HumanMessage(content=prompt),
                ]
            ),
            attempts=gateway.settings.retry_max_attempts,
            base_delay=gateway.settings.retry_base_delay_s,
            max_delay=gateway.settings.retry_max_delay_s,
        )
        raw = result.get("raw") if isinstance(result, dict) else None
        if raw is not None:
            gateway.record_usage(raw)
        return result.get("parsed") if isinstance(result, dict) else None
    except Exception as exc:
        logger.warning("single shot regeneration failed: %s", exc)
        return None


def _local_regenerate_shot(
    brief: PromptBrief,
    current: PromptShot,
    locked: set[str],
    catalog_path: str = "",
) -> PromptShot:
    catalog = load_catalog(catalog_path)
    candidate = current.model_copy(deep=True)
    seed = int(
        hashlib.sha1(f"{current.prompt}:{uuid.uuid4().hex}".encode("utf-8")).hexdigest()[:8],
        16,
    )
    if "shot_type" not in locked:
        candidate.shot_type = catalog["shot_types"][seed % len(catalog["shot_types"])]
    if "camera_movement" not in locked:
        candidate.camera_movement = catalog["camera_moves"][
            (seed // 3) % len(catalog["camera_moves"])
        ]
    if "lighting" not in locked:
        candidate.lighting = catalog["lighting"][
            (seed // 5) % len(catalog["lighting"])
        ]
    if "transition" not in locked:
        candidate.transition = catalog["transitions"][
            (seed // 7) % len(catalog["transitions"])
        ]
    if "color_palette" not in locked:
        candidate.color_palette = catalog["palettes"][
            (seed // 11) % len(catalog["palettes"])
        ]
    if "prompt" not in locked:
        candidate.prompt = _compose_prompt(
            candidate,
            brief,
            brief.style or "cinematic natural style",
        )
    return candidate
