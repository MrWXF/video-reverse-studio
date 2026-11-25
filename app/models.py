from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="未命名项目")
    source_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), default="uploaded", index=True)
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    fps: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    shots: Mapped[list["Shot"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Shot.index",
    )
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    edit_events: Mapped[list["ShotEditEvent"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class Shot(Base):
    __tablename__ = "shots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    index: Mapped[int] = mapped_column(Integer)
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    keyframe_path: Mapped[str] = mapped_column(String(500), default="")
    transcript: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(30), default="unknown")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)

    project: Mapped["Project"] = relationship(back_populates="shots")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    step: Mapped[str] = mapped_column(String(50), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str] = mapped_column(Text, default="")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped["Project"] = relationship(back_populates="jobs")


class PromptProject(Base):
    __tablename__ = "prompt_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="未命名提示词")
    source_project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reference_mode: Mapped[str] = mapped_column(String(20), default="style")
    reference_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    entity_bible_json: Mapped[dict] = mapped_column(JSON, default=dict)
    brief_json: Mapped[dict] = mapped_column(JSON, default=dict)
    plan_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    step: Mapped[str] = mapped_column(String(50), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str] = mapped_column(Text, default="")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    versions: Mapped[list["PromptVersion"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="PromptVersion.version",
    )
    reviews: Mapped[list["DeliveryReview"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    shares: Mapped[list["PromptShare"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    prompt_project_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_projects.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    title: Mapped[str] = mapped_column(String(200), default="")
    brief_json: Mapped[dict] = mapped_column(JSON, default=dict)
    entity_bible_json: Mapped[dict] = mapped_column(JSON, default=dict)
    plan_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped["PromptProject"] = relationship(back_populates="versions")


class DeliveryReview(Base):
    __tablename__ = "delivery_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    prompt_project_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_projects.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(300), default="")
    source_path: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    step: Mapped[str] = mapped_column(String(50), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str] = mapped_column(Text, default="")
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped["PromptProject"] = relationship(back_populates="reviews")


class PromptShare(Base):
    __tablename__ = "prompt_shares"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    prompt_project_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_projects.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[str | None] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="SET NULL"), nullable=True
    )
    token: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    permission: Mapped[str] = mapped_column(String(20), default="read")
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped["PromptProject"] = relationship(back_populates="shares")
    comments: Mapped[list["PromptComment"]] = relationship(
        back_populates="share",
        cascade="all, delete-orphan",
    )


class PromptComment(Base):
    __tablename__ = "prompt_comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    share_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_shares.id", ondelete="CASCADE"), index=True
    )
    author: Mapped[str] = mapped_column(String(80), default="访客")
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    share: Mapped["PromptShare"] = relationship(back_populates="comments")


class ShotTemplate(Base):
    """A reusable shot style saved from a completed reverse-analysis shot."""

    __tablename__ = "shot_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(50), default="自定义", index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)

    shot_type: Mapped[str] = mapped_column(String(80), default="")
    camera_movement: Mapped[str] = mapped_column(String(100), default="")
    lighting: Mapped[str] = mapped_column(String(200), default="")
    visual_style: Mapped[str] = mapped_column(String(300), default="")
    color_palette: Mapped[list[str]] = mapped_column(JSON, default=list)
    prompt_template: Mapped[str] = mapped_column(Text, default="")
    negative_prompt: Mapped[str] = mapped_column(Text, default="")
    transition: Mapped[str] = mapped_column(String(100), default="")
    remake_notes: Mapped[str] = mapped_column(Text, default="")

    source_project_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    source_shot_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ShotEditEvent(Base):
    """Immutable audit record used by the future analysis-quality dashboard."""

    __tablename__ = "shot_edit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    shot_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    shot_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="manual_edit")
    changes: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped["Project"] = relationship(back_populates="edit_events")
