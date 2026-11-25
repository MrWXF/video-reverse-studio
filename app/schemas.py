from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Origin = Literal["filmed", "ai_generated", "code_generated", "unknown"]
PromptLanguage = Literal["en", "zh"]
ReferenceMode = Literal["style", "structure", "full"]
TemplateField = Literal[
    "shot_type",
    "camera_movement",
    "lighting",
    "color_palette",
    "transition",
    "prompt",
    "negative_prompt",
    "remake_notes",
]


class ShotAnalysis(BaseModel):
    shot_type: str = Field(default="中景", description="景别")
    camera_movement: str = Field(default="固定", description="运镜")
    subject: str = Field(default="", description="画面主体")
    scene: str = Field(default="", description="场景环境")
    visual_style: str = Field(default="", description="视觉风格")
    lighting: str = Field(default="", description="光线")
    color_palette: list[str] = Field(default_factory=list, description="主要颜色")
    origin: Origin = Field(default="unknown", description="镜头来源判定")
    confidence: float = Field(default=0.0, ge=0, le=1, description="来源判定置信度")
    evidence: list[str] = Field(default_factory=list, description="判定依据")
    prompt: str = Field(default="", description="复刻该镜头的英文提示词")
    remake_notes: str = Field(default="", description="复刻注意事项")


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class RecipeShot(BaseModel):
    index: int
    start_s: float
    end_s: float
    duration: float
    shot_type: str
    camera_movement: str
    subject: str
    scene: str
    visual_style: str
    lighting: str
    color_palette: list[str] = Field(default_factory=list)
    origin: str
    confidence: float
    evidence: list[str] = Field(default_factory=list)
    prompt: str
    remake_notes: str
    transcript: str = ""


class Recipe(BaseModel):
    title: str
    source_filename: str
    duration: float
    width: int
    height: int
    fps: float
    shots: list[RecipeShot]
    cut_count: int
    cuts_per_minute: float
    avg_shot_seconds: float
    pacing: str
    origin_counts: dict[str, int]
    summary: str
    generated_at: datetime


class ReferenceContext(BaseModel):
    project_id: str
    mode: ReferenceMode = "style"
    recipe: Recipe


class EntityItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=1000)
    appearance: str = Field(default="", max_length=1000)
    must_keep: list[str] = Field(default_factory=list)


class EntityBible(BaseModel):
    characters: list[EntityItem] = Field(default_factory=list)
    products: list[EntityItem] = Field(default_factory=list)
    wardrobe: list[EntityItem] = Field(default_factory=list)
    scenes: list[EntityItem] = Field(default_factory=list)
    consistency_rules: list[str] = Field(default_factory=list)


class PromptBrief(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(default="", max_length=200)
    idea: str = Field(min_length=2, max_length=2000)
    target_model: str = Field(default="generic", max_length=80)
    language: PromptLanguage = "en"
    duration_s: float = Field(default=15.0, ge=3.0, le=120.0)
    aspect_ratio: str = Field(default="16:9", max_length=20)
    shot_count: int = Field(default=4, ge=1, le=8)
    style: str = Field(default="", max_length=500)
    mood: str = Field(default="", max_length=500)
    audience: str = Field(default="", max_length=500)
    negative_prompt: str = Field(default="", max_length=1000)
    constraints: list[str] = Field(default_factory=list)
    reference_project_id: str | None = None
    reference_mode: ReferenceMode = "style"
    entity_bible: EntityBible = Field(default_factory=EntityBible)


class ShotAnalysisUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    shot_type: str | None = None
    camera_movement: str | None = None
    subject: str | None = None
    scene: str | None = None
    visual_style: str | None = None
    lighting: str | None = None
    color_palette: list[str] | None = None
    origin: Origin | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: list[str] | None = None
    prompt: str | None = None
    remake_notes: str | None = None
    transcript: str | None = None


class ShotTemplateSave(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    category: str = Field(default="自定义", max_length=50)
    tags: list[str] = Field(default_factory=list)


class ShotTemplateApply(BaseModel):
    template_id: int = Field(ge=1)
    shot_indices: list[int] = Field(default_factory=list)
    fields: list[TemplateField] = Field(
        default_factory=lambda: [
            "shot_type",
            "camera_movement",
            "lighting",
            "color_palette",
            "transition",
        ]
    )


class PromptShot(BaseModel):
    index: int = Field(default=1, ge=1)
    start_s: float = Field(default=0.0, ge=0.0)
    end_s: float = Field(default=0.0, ge=0.0)
    duration: float = Field(default=0.0, ge=0.0)
    shot_type: str = Field(default="中景")
    camera_movement: str = Field(default="固定")
    subject: str = Field(default="")
    action: str = Field(default="")
    scene: str = Field(default="")
    lighting: str = Field(default="")
    color_palette: list[str] = Field(default_factory=list)
    prompt: str = Field(default="")
    negative_prompt: str = Field(default="")
    transition: str = Field(default="")
    remake_notes: str = Field(default="")
    source_shot_index: int | None = Field(default=None, ge=1)
    locked_fields: list[str] = Field(default_factory=list)


class PromptShotUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    shot_type: str | None = None
    camera_movement: str | None = None
    subject: str | None = None
    action: str | None = None
    scene: str | None = None
    lighting: str | None = None
    color_palette: list[str] | None = None
    prompt: str | None = None
    negative_prompt: str | None = None
    transition: str | None = None
    remake_notes: str | None = None
    locked_fields: list[str] | None = None


class GenerationJobCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    shot_indices: list[int] = Field(default_factory=list)
    aspect_ratio: str = Field(default="", max_length=20)
    model: str = Field(default="", max_length=80)
    idempotency_key: str | None = Field(default=None, max_length=120)


class CostEstimateRequest(BaseModel):
    video_duration: float = Field(gt=0, le=10800)
    estimated_shots: int | None = Field(default=None, ge=1, le=1000)


class ShareCreate(BaseModel):
    permission: Literal["read", "comment"] = "read"
    expires_in_days: int | None = Field(default=None, ge=1, le=365)
    version_id: str | None = None


class CommentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    author: str = Field(default="访客", max_length=80)
    content: str = Field(min_length=1, max_length=2000)


class PromptPlan(BaseModel):
    title: str = Field(default="")
    summary: str = Field(default="")
    target_model: str = Field(default="generic")
    language: PromptLanguage = "en"
    duration_s: float = Field(default=15.0, ge=0.0)
    aspect_ratio: str = Field(default="16:9")
    global_style: str = Field(default="")
    target_profile: dict = Field(default_factory=dict)
    shots: list[PromptShot] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
