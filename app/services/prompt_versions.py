"""Create immutable prompt-plan snapshots and serialize version metadata."""

import copy
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import PromptProject, PromptVersion


def create_prompt_version(
    db: Session,
    project: PromptProject,
    source: str,
) -> PromptVersion:
    """Add the next immutable version snapshot without committing the transaction."""
    latest = db.scalar(
        select(func.max(PromptVersion.version)).where(
            PromptVersion.prompt_project_id == project.id
        )
    )
    version = PromptVersion(
        id=str(uuid.uuid4()),
        prompt_project_id=project.id,
        version=int(latest or 0) + 1,
        source=source[:40],
        title=project.title,
        brief_json=copy.deepcopy(project.brief_json or {}),
        entity_bible_json=copy.deepcopy(project.entity_bible_json or {}),
        plan_json=copy.deepcopy(project.plan_json or {}),
        created_at=datetime.now(timezone.utc),
    )
    db.add(version)
    return version


def version_payload(version: PromptVersion, include_plan: bool = False) -> dict:
    """Serialize version metadata and optionally its full snapshots."""
    plan = version.plan_json or {}
    payload = {
        "id": version.id,
        "version": version.version,
        "source": version.source,
        "title": version.title,
        "shot_count": len(plan.get("shots") or []),
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }
    if include_plan:
        payload["plan"] = plan
        payload["brief"] = version.brief_json or {}
        payload["entity_bible"] = version.entity_bible_json or {}
    return payload
