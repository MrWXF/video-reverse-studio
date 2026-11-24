import hashlib
import json
import logging
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser

from ..config import Settings, get_settings
from ..db import SessionLocal
from ..models import PromptProject
from ..prompts import load_prompt
from ..schemas import PromptBrief, PromptPlan, PromptShot
from .llm import LLMGateway

logger = logging.getLogger(__name__)

_SHOT_TYPES = ["远景", "全景", "中景", "近景", "特写", "大特写"]
_MOVES = ["固定", "缓慢推镜", "横移", "跟拍", "环绕", "升降"]
_LIGHTING = ["自然柔光", "侧逆光", "暖色轮廓光", "冷色环境光", "高对比硬光"]
_TRANSITIONS = ["直切", "叠化", "遮挡转场", "动作衔接", "淡入淡出"]
_PALETTES = [
    ["#0f172a", "#38bdf8", "#e2e8f0"],
    ["#1c1917", "#f59e0b", "#fef3c7"],
    ["#052e16", "#22c55e", "#dcfce7"],
    ["#3b0764", "#a855f7", "#f3e8ff"],
]


def _update_project(
    db,
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


def run_prompt_generation(project_id: str) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        project = db.get(PromptProject, project_id)
        if project is None:
            logger.error("prompt project missing: %s", project_id)
            return

        try:
            brief = PromptBrief.model_validate(project.brief_json or {})
            _update_project(db, project, status="running", step="planning", progress=0.15)
            gateway = LLMGateway(settings)
            plan, notes = generate_prompt_plan(brief, gateway)
            _update_project(db, project, step="validating", progress=0.85)
            plan = normalize_prompt_plan(plan, brief)
            plan.warnings.extend(notes)

            project.title = plan.title or project.title
            project.plan_json = plan.model_dump(mode="json")
            project.metrics = gateway.stats()
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
            project.status = "failed"
            project.step = "failed"
            project.error = str(exc)[:2000]
            project.updated_at = datetime.now(timezone.utc)
            db.commit()


def generate_prompt_plan(
    brief: PromptBrief,
    gateway: LLMGateway,
) -> tuple[PromptPlan, list[str]]:
    if not gateway.enabled:
        return mock_prompt_plan(brief), ["Mock 模式：未调用文本模型"]

    llm = gateway.chat_model()
    if llm is None:
        return mock_prompt_plan(brief), ["未配置文本模型，已使用 Mock 方案"]

    messages = [
        SystemMessage(content=load_prompt("video_prompt_generation")),
        HumanMessage(content=_brief_text(brief)),
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
        raise RuntimeError(f"提示词生成失败：{str(exc)[:500]}") from exc


def _brief_text(brief: PromptBrief) -> str:
    payload = json.dumps(brief.model_dump(mode="json"), ensure_ascii=False, indent=2)
    return (
        "请根据以下创意简报生成视频提示词方案。"
        "严格按 schema 输出，不要输出 Markdown 代码块。\n\n"
        f"{payload}"
    )


def normalize_prompt_plan(
    plan: PromptPlan,
    brief: PromptBrief,
    *,
    generated_at: datetime | None = None,
) -> PromptPlan:
    shots = sorted(plan.shots, key=lambda item: item.index)
    if not shots:
        raise RuntimeError("模型未返回任何镜头")

    warnings = list(plan.warnings)
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

    for index, (shot, raw_duration) in enumerate(zip(shots, durations), start=1):
        duration = round(raw_duration * scale, 3)
        if index == len(shots):
            duration = round(brief.duration_s - cursor, 3)
        duration = max(0.1, duration)
        shot.index = index
        shot.start_s = round(cursor, 3)
        shot.end_s = round(cursor + duration, 3)
        shot.duration = duration
        cursor = shot.end_s
        shot.prompt = shot.prompt.strip() or _compose_prompt(shot, brief)
        shot.negative_prompt = shot.negative_prompt or brief.negative_prompt
        shot.shot_type = shot.shot_type or "中景"
        shot.camera_movement = shot.camera_movement or "固定"
        shot.transition = shot.transition or _TRANSITIONS[(index - 1) % len(_TRANSITIONS)]
        normalized_shots.append(shot)

    plan.title = plan.title.strip() or brief.title.strip() or brief.idea[:40]
    plan.summary = plan.summary.strip() or (
        f"围绕“{brief.idea[:80]}”生成 {len(normalized_shots)} 个可执行镜头。"
    )
    plan.target_model = brief.target_model
    plan.language = brief.language
    plan.duration_s = brief.duration_s
    plan.aspect_ratio = brief.aspect_ratio
    plan.global_style = plan.global_style.strip() or brief.style or "cinematic natural style"
    plan.shots = normalized_shots
    plan.warnings = warnings
    plan.generated_at = generated_at or datetime.now(timezone.utc)
    return plan


def _compose_prompt(shot: PromptShot, brief: PromptBrief) -> str:
    subject = shot.subject or "the main subject"
    action = shot.action or "performs a clear, visually readable action"
    scene = shot.scene or "a clean cinematic environment"
    lighting = shot.lighting or "cinematic natural lighting"
    style = brief.style or "commercial film look"
    mood = brief.mood or "clear and engaging"
    return (
        f"{shot.shot_type} shot of {subject}, {action}, in {scene}, "
        f"{shot.camera_movement}, {lighting}, {style}, {mood} mood, "
        f"{brief.aspect_ratio} aspect ratio, optimized for {brief.target_model}, "
        "detailed texture, realistic motion, high production value"
    )


def mock_prompt_plan(brief: PromptBrief) -> PromptPlan:
    seed = int(hashlib.sha1(brief.idea.encode("utf-8")).hexdigest()[:8], 16)
    count = brief.shot_count
    step = brief.duration_s / count
    shots: list[PromptShot] = []

    for index in range(1, count + 1):
        local = seed + index * 31
        shot_type = _SHOT_TYPES[local % len(_SHOT_TYPES)]
        movement = _MOVES[(local // 3) % len(_MOVES)]
        lighting = _LIGHTING[(local // 5) % len(_LIGHTING)]
        transition = _TRANSITIONS[(local // 7) % len(_TRANSITIONS)]
        palette = _PALETTES[(local // 11) % len(_PALETTES)]
        start_s = round((index - 1) * step, 3)
        end_s = round(index * step, 3)
        shot = PromptShot(
            index=index,
            start_s=start_s,
            end_s=end_s,
            duration=round(step, 3),
            shot_type=shot_type,
            camera_movement=movement,
            subject="the product or protagonist",
            action="a clear, purposeful action",
            scene="a clean cinematic environment",
            lighting=lighting,
            color_palette=palette,
            prompt="",
            negative_prompt=brief.negative_prompt,
            transition=transition,
            remake_notes="Mock 方案仅用于流程演示，配置文本模型后可生成真实创意。",
        )
        shot.prompt = _compose_prompt(shot, brief)
        shots.append(shot)

    return PromptPlan(
        title=brief.title or "未命名提示词方案",
        summary=f"为“{brief.idea[:80]}”生成 {count} 个镜头的 Mock 提示词方案。",
        target_model=brief.target_model,
        language=brief.language,
        duration_s=brief.duration_s,
        aspect_ratio=brief.aspect_ratio,
        global_style=brief.style or "cinematic natural style",
        shots=shots,
        assumptions=["Mock 模式不调用模型，结果仅用于流程演示。"],
        warnings=["Mock 模式：未调用文本模型"],
    )
