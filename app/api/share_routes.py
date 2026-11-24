import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import PROJECT_ROOT
from ..db import get_db
from ..models import PromptComment, PromptShare, PromptVersion
from ..schemas import CommentCreate
from ..serializers import comment_payload, prompt_project_payload

router = APIRouter()
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def get_active_share(db: Session, token: str) -> PromptShare:
    share = db.scalar(select(PromptShare).where(PromptShare.token == token))
    if share is None or share.revoked_at is not None:
        raise HTTPException(status_code=404, detail="分享链接不存在或已失效")
    expires_at = _utc(share.expires_at)
    if expires_at and expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="分享链接已过期")
    return share


def _shared_project_payload(share: PromptShare, db: Session) -> dict:
    payload = prompt_project_payload(share.project, include_plan=True)
    version = db.get(PromptVersion, share.version_id) if share.version_id else None
    if version is not None and version.prompt_project_id == share.prompt_project_id:
        payload["title"] = version.title or payload["title"]
        payload["plan"] = version.plan_json or {}
        payload["brief"] = version.brief_json or {}
        payload["entity_bible"] = version.entity_bible_json or {}
        payload["version_number"] = version.version
    else:
        payload["version_number"] = None
    payload["read_only"] = True
    payload["share"] = {
        "permission": share.permission,
        "expires_at": share.expires_at.isoformat() if share.expires_at else None,
        "version_number": payload["version_number"],
    }
    return payload


@router.get("/share/{token}", response_class=HTMLResponse)
def share_page(token: str, request: Request, db: Session = Depends(get_db)):
    share = get_active_share(db, token)
    return templates.TemplateResponse(
        request,
        "share.html",
        {
            "request": request,
            "token": token,
            "title": share.project.title,
            "permission": share.permission,
        },
    )


@router.get("/api/shares/{token}")
def get_shared_prompt(token: str, db: Session = Depends(get_db)) -> dict:
    share = get_active_share(db, token)
    return _shared_project_payload(share, db)


@router.get("/api/shares/{token}/comments")
def list_shared_comments(token: str, db: Session = Depends(get_db)) -> list[dict]:
    share = get_active_share(db, token)
    comments = db.scalars(
        select(PromptComment)
        .where(PromptComment.share_id == share.id)
        .order_by(PromptComment.created_at)
    ).all()
    return [comment_payload(comment) for comment in comments]


@router.post("/api/shares/{token}/comments", status_code=201)
def create_shared_comment(
    token: str,
    comment: CommentCreate,
    db: Session = Depends(get_db),
) -> dict:
    share = get_active_share(db, token)
    if share.permission != "comment":
        raise HTTPException(status_code=403, detail="该分享链接仅支持只读浏览")
    item = PromptComment(
        id=str(uuid.uuid4()),
        share_id=share.id,
        author=comment.author.strip() or "访客",
        content=comment.content,
        created_at=datetime.now(timezone.utc),
    )
    db.add(item)
    db.commit()
    return comment_payload(item)
