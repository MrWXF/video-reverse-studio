import json

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import PROJECT_ROOT
from ..schemas import Recipe

_TEMPLATE_DIR = PROJECT_ROOT / "app" / "templates"
_ORIGIN_LABELS = {
    "filmed": "实拍",
    "ai_generated": "AI 生成",
    "code_generated": "代码/3D 生成",
    "unknown": "未知",
}
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_markdown(recipe: Recipe) -> str:
    template = _env.get_template("video.md.j2")
    return template.render(
        recipe=recipe,
        origin_label=lambda key: _ORIGIN_LABELS.get(key, "未知"),
    )


def render_json(recipe: Recipe) -> str:
    return json.dumps(recipe.model_dump(mode="json"), ensure_ascii=False, indent=2)