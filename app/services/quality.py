"""Analysis-quality aggregation built from human edit events and job metrics."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from statistics import fmean

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Job, Project, ShotEditEvent

FIELD_LABELS = {
    "origin": "来源判定",
    "shot_type": "景别",
    "camera_movement": "运镜",
    "subject": "主体",
    "scene": "场景",
    "visual_style": "视觉风格",
    "lighting": "光线",
    "color_palette": "色板",
    "confidence": "置信度",
    "evidence": "证据",
    "prompt": "提示词",
    "remake_notes": "复刻备注",
    "transcript": "旁白 / 转写",
}


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize a datetime to timezone-aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _ratio(numerator: int, denominator: int) -> float | None:
    """Return a rounded ratio, or ``None`` when the denominator is zero."""
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _shot_key(event: ShotEditEvent) -> tuple[str, str | int]:
    """Build a stable project/shot key for grouping edit events."""
    if event.shot_id is not None:
        return event.project_id, event.shot_id
    return event.project_id, f"index:{event.shot_index}"


def _has_field(event: ShotEditEvent, field: str) -> bool:
    """Return whether an edit event changed the requested field."""
    return field in (event.changes or {})


def build_quality_dashboard(
    db: Session,
    days: int = 30,
    now: datetime | None = None,
) -> dict:
    """Aggregate quality signals for projects active in the requested window.

    A project is in scope when it was created, completed an analysis job, or
    received an edit event within the window. This keeps the denominator tied
    to projects the team is actually working on, rather than diluting the rate
    with historical projects that were never touched again.
    """

    now_utc = _as_utc(now) or datetime.now(timezone.utc)
    days = max(1, int(days))
    end_date = now_utc.date()
    start_date = end_date - timedelta(days=days - 1)
    cutoff = datetime.combine(start_date, time.min, tzinfo=timezone.utc)

    projects = db.scalars(
        select(Project).options(selectinload(Project.shots))
    ).all()
    jobs = db.scalars(select(Job)).all()
    events = db.scalars(select(ShotEditEvent)).all()

    active_project_ids: set[str] = set()
    for project in projects:
        created_at = _as_utc(project.created_at)
        if created_at is not None and created_at >= cutoff:
            active_project_ids.add(project.id)

    recent_events: list[ShotEditEvent] = []
    for event in events:
        created_at = _as_utc(event.created_at)
        if created_at is not None and created_at >= cutoff:
            recent_events.append(event)
            active_project_ids.add(event.project_id)

    completed_jobs: list[Job] = []
    for job in jobs:
        if job.status != "done":
            continue
        updated_at = _as_utc(job.updated_at)
        if updated_at is not None and updated_at >= cutoff:
            active_project_ids.add(job.project_id)
            completed_jobs.append(job)

    scoped_projects = [project for project in projects if project.id in active_project_ids]
    shot_counts = {project.id: len(project.shots or []) for project in scoped_projects}
    total_shots = sum(shot_counts.values())
    total_projects = len(scoped_projects)

    edited_shot_keys = {_shot_key(event) for event in recent_events}
    origin_events = [event for event in recent_events if _has_field(event, "origin")]
    origin_shot_keys = {_shot_key(event) for event in origin_events}
    origin_accuracy = (
        1.0 - len(origin_shot_keys) / total_shots
        if total_shots > 0 and recent_events
        else None
    )

    field_counts: Counter[str] = Counter()
    field_shot_keys: dict[str, set[tuple[str, str | int]]] = defaultdict(set)
    for event in recent_events:
        key = _shot_key(event)
        for field in (event.changes or {}):
            field_counts[field] += 1
            field_shot_keys[field].add(key)

    fields = [
        {
            "field": field,
            "label": FIELD_LABELS.get(field, field),
            "count": count,
            "affected_shots": len(field_shot_keys[field]),
            "rate": _ratio(len(field_shot_keys[field]), total_shots),
        }
        for field, count in field_counts.most_common()
    ]

    durations: list[float] = []
    total_tokens = 0
    total_calls = 0
    for job in completed_jobs:
        created_at = _as_utc(job.created_at)
        updated_at = _as_utc(job.updated_at)
        if created_at is not None and updated_at is not None:
            duration = (updated_at - created_at).total_seconds()
            if 0 <= duration <= 7200:
                durations.append(duration)
        metrics = job.metrics or {}
        total_calls += int(metrics.get("calls") or 0)
        total_tokens += int(metrics.get("prompt_tokens") or 0) + int(
            metrics.get("completion_tokens") or 0
        )

    event_counts_by_project = Counter(event.project_id for event in recent_events)
    edited_by_project: dict[str, set[tuple[str, str | int]]] = defaultdict(set)
    origin_by_project: Counter[str] = Counter()
    last_edit_by_project: dict[str, datetime] = {}
    for event in recent_events:
        edited_by_project[event.project_id].add(_shot_key(event))
        if _has_field(event, "origin"):
            origin_by_project[event.project_id] += 1
        created_at = _as_utc(event.created_at)
        if created_at is not None:
            prior = last_edit_by_project.get(event.project_id)
            if prior is None or created_at > prior:
                last_edit_by_project[event.project_id] = created_at

    project_rows = []
    for project in sorted(
        scoped_projects,
        key=lambda item: (
            event_counts_by_project.get(item.id, 0),
            _as_utc(item.created_at) or cutoff,
        ),
        reverse=True,
    )[:10]:
        last_edit = last_edit_by_project.get(project.id)
        project_rows.append(
            {
                "id": project.id,
                "title": project.title,
                "status": project.status,
                "shot_count": shot_counts.get(project.id, 0),
                "edit_events": event_counts_by_project.get(project.id, 0),
                "edited_shots": len(edited_by_project.get(project.id, set())),
                "origin_corrections": origin_by_project.get(project.id, 0),
                "last_edit_at": last_edit.isoformat() if last_edit else None,
            }
        )

    trend_buckets: dict[str, dict] = {}
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        key = day.isoformat()
        trend_buckets[key] = {
            "date": key,
            "edit_events": 0,
            "field_corrections": 0,
            "origin_corrections": 0,
            "edited_shots": set(),
        }
    for event in recent_events:
        created_at = _as_utc(event.created_at)
        if created_at is None:
            continue
        key = created_at.date().isoformat()
        bucket = trend_buckets.get(key)
        if bucket is None:
            continue
        bucket["edit_events"] += 1
        bucket["field_corrections"] += len(event.changes or {})
        if _has_field(event, "origin"):
            bucket["origin_corrections"] += 1
        bucket["edited_shots"].add(_shot_key(event))

    trend = []
    for bucket in trend_buckets.values():
        trend.append(
            {
                **{key: value for key, value in bucket.items() if key != "edited_shots"},
                "edited_shots": len(bucket["edited_shots"]),
            }
        )

    average_processing_seconds = round(fmean(durations), 2) if durations else None
    suggestions: list[str] = []
    if total_projects == 0:
        suggestions.append("当前时间窗口内没有分析或编辑活动，先上传视频并修正几个镜头。")
    if recent_events:
        origin_rate = _ratio(len(origin_shot_keys), total_shots)
        if origin_rate is not None and origin_rate >= 0.15:
            suggestions.append(
                f"来源判定修正涉及 {origin_rate:.0%} 的镜头，建议检查实拍/AI 证据提取，"
                "并在界面上强化低置信度提示。"
            )
        top_field = next((item for item in fields if item["field"] != "origin"), None)
        if top_field and top_field["rate"] is not None and top_field["rate"] >= 0.2:
            suggestions.append(
                f"{top_field['label']}修正率较高（{top_field['rate']:.0%}），"
                "建议在提示词中补充该项的判定依据和示例。"
            )
    if average_processing_seconds is not None and average_processing_seconds > 120:
        suggestions.append(
            f"平均分析耗时 {average_processing_seconds:.1f} 秒，建议检查关键帧抽取和模型并发配置。"
        )
    if total_tokens:
        suggestions.append(
            f"窗口内完成分析共消耗 {total_tokens:,} token；可结合成本预估控制镜头数量。"
        )
    if total_shots and total_shots < 10:
        suggestions.append("当前样本量较小，来源准确率和字段趋势仅作为方向参考。")
    suggestions.append("指标来自人工修正事件，不等同于模型真实准确率或法律意义上的检测结论。")

    return {
        "generated_at": now_utc.isoformat(),
        "window": {
            "days": days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "summary": {
            "projects": total_projects,
            "shots": total_shots,
            "edit_events": len(recent_events),
            "edited_shots": len(edited_shot_keys),
            "origin_corrections": len(origin_shot_keys),
            "origin_accuracy": round(origin_accuracy, 4)
            if origin_accuracy is not None
            else None,
            "correction_rate": _ratio(len(edited_shot_keys), total_shots),
            "analysis_runs": len(completed_jobs),
            "average_processing_seconds": average_processing_seconds,
            "total_tokens": total_tokens,
            "total_calls": total_calls,
        },
        "fields": fields,
        "trend": trend,
        "projects": project_rows,
        "suggestions": suggestions,
        "note": "统计范围包含窗口内创建、完成分析或发生编辑的项目。",
    }
