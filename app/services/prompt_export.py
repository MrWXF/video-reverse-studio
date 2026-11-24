import json

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import PROJECT_ROOT
from ..schemas import PromptPlan

_TEMPLATE_DIR = PROJECT_ROOT / "app" / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_prompt_markdown(plan: PromptPlan) -> str:
    template = _env.get_template("prompt_plan.md.j2")
    return template.render(plan=plan)


def render_prompt_json(plan: PromptPlan) -> str:
    return json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2)
