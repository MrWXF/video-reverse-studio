import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app import security
from app.config import Settings, get_settings
from app.main import app


@pytest.fixture
def ui_client(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    get_settings.cache_clear()
    settings = Settings(data_dir=tmp_path, app_password="")
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    yield TestClient(app)
    get_settings.cache_clear()


def test_home_renders_both_workspaces(ui_client):
    response = ui_client.get("/")

    assert response.status_code == 200
    for marker in [
        'id="reverse-view"',
        'id="generate-view"',
        'id="prompt-form"',
        'id="prompt-idea"',
        'id="projects-count"',
        'id="prompt-projects-count"',
        'class="mode-tab active"',
    ]:
        assert marker in response.text


def test_frontend_assets_expose_design_system_hooks():
    root = Path(__file__).resolve().parent.parent
    html = (root / "app" / "templates" / "index.html").read_text(encoding="utf-8")
    css = (root / "app" / "static" / "style.css").read_text(encoding="utf-8")
    app_js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    prompt_js = (root / "app" / "static" / "prompt.js").read_text(encoding="utf-8")
    shared_js = (root / "app" / "static" / "shared.js").read_text(encoding="utf-8")

    assert 'data-style="a"' in html
    assert 'data-style-option="a"' in html
    assert 'data-style-option="b"' in html
    assert "style-switch" in html
    assert 'data-mode-target="generate"' in html
    assert "--accent: #6c5ce7" in css
    assert "--accent: #54e8ff" in css
    assert ".plan-overview" in css
    assert "@media (max-width: 940px)" in css
    assert "project-copy" in app_js
    assert "plan-overview" in prompt_js
    assert "data-status" in prompt_js
    assert "data-copy-text" in prompt_js
    assert 'data-reference-mode="full"' in app_js
    assert 'id="prompt-reference"' in html
    assert 'id="prompt-reference-mode"' in html
    assert 'id="reference-preview"' in html
    assert "data-open-reference" in prompt_js
    assert "reference-source-card" in prompt_js
    assert "data-edit-shot" in app_js
    assert "data-shot-editor" in app_js
    assert "data-prompt-shot-editor" in prompt_js
    assert "data-entity-form" in prompt_js
    assert "data-restore-version" in prompt_js
    assert "data-version-compare" in prompt_js
    assert "comparePromptVersions" in prompt_js
    assert "data-toggle-share-qr" in prompt_js
    assert ".version-compare-kpis" in css
    assert ".share-qr-card" in css
    assert "comparison-summary" in prompt_js
    assert ".prompt-studio-tools" in css
    assert ".field-locks" in css
    assert 'id="template-prompt-template"' in html
    assert "data-insert-template-placeholder" in html
    assert "template-category-filter" in prompt_js
    assert "template-tag-filters" in prompt_js
    assert "/api/shot-templates/facets" in prompt_js
    assert ".template-tag-chip.is-selected" in css
    assert ".template-placeholder-badge" in css
    assert "global.ReelReverse" in shared_js
    assert "window.ReelReverse" in app_js
    assert "window.ReelReverse" in prompt_js


def test_timeline_editor_hooks_are_present():
    root = Path(__file__).resolve().parent.parent
    css = (root / "app" / "static" / "style.css").read_text(encoding="utf-8")
    app_js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")

    assert "function timelineMarkup" in app_js
    assert "timelineContext" in app_js
    assert "data-timeline-boundary" in app_js
    assert "data-timeline-split" in app_js
    assert "data-timeline-merge" in app_js
    assert "data-timeline-reanalyze" in app_js
    assert "/boundary" in app_js
    assert '"PATCH"' in app_js
    assert "pointerdown" in app_js
    assert "pointermove" in app_js
    assert "pointerup" in app_js
    assert "ArrowLeft" in app_js
    assert "ArrowRight" in app_js
    assert "timeline_min_shot_seconds" in app_js
    assert "timeline_queued" in app_js
    assert "timeline_analyzing" in app_js
    assert app_js.index("mediaBlock +") < app_js.index("timelineBlock +")
    assert ".shot-timeline" in css
    assert ".timeline-track" in css
    assert ".timeline-segment.is-selected" in css
    assert ".timeline-handle" in css
    assert ".timeline-actions" in css
    assert 'html[data-style="b"] .shot-timeline' in css


def test_react_app_serves_built_entrypoint(ui_client):
    response = ui_client.get("/app")

    assert response.status_code == 200
    assert 'id="root"' in response.text
    assert 'href="/static/favicon.svg"' in response.text
    assets = sorted(
        set(re.findall(r'(?:src|href)="(/static/react/assets/[^"]+)"', response.text))
    )
    assert any(path.endswith(".js") for path in assets)
    assert any(path.endswith(".css") for path in assets)
    for asset in assets:
        assert ui_client.get(asset).status_code == 200

    nested = ui_client.get("/app/reverse/demo-project")
    assert nested.status_code == 200
    assert 'id="root"' in nested.text

    favicon = ui_client.get("/static/favicon.svg")
    assert favicon.status_code == 200
    assert "<svg" in favicon.text


def test_react_app_reports_missing_build(ui_client, monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "react_index", tmp_path / "missing-index.html")

    response = ui_client.get("/app")

    assert response.status_code == 404
    assert "npm run build" in response.json()["detail"]


def test_docs_serves_api_reference_page(ui_client):
    response = ui_client.get("/docs")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "ReelReverse · API 文档" in response.text
    # The page is the hand-written reference, not the Swagger UI scaffold.
    assert "swagger-ui" not in response.text.lower()
    # The machine-readable schema stays available for tooling.
    assert ui_client.get("/openapi.json").status_code == 200


def test_react_reverse_workspace_includes_timeline_and_safe_delete():
    root = Path(__file__).resolve().parent.parent
    detail = (root / "web" / "src" / "features" / "reverse" / "ProjectDetail.tsx").read_text(
        encoding="utf-8"
    )
    timeline = (
        root / "web" / "src" / "features" / "reverse" / "TimelineEditor.tsx"
    ).read_text(encoding="utf-8")

    assert "TimelineEditor" in detail
    assert "if (deleted)" in detail
    assert "data-timeline-boundary" in timeline
    assert "data-timeline-split" in timeline
    assert "data-timeline-merge" in timeline
    assert "data-timeline-reanalyze" in timeline
    assert "onPointerMove" in timeline
    assert "ArrowLeft" in timeline
    assert "timeline_min_shot_seconds" in timeline


def _global_declarations(source: str) -> set[str]:
    names = set(
        re.findall(r"(?m)^(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)", source)
    )
    for block in re.findall(
        r"(?ms)^const\s*\{(.*?)\}\s*=\s*window\.ReelReverse;", source
    ):
        for item in block.split(","):
            value = item.split(":", 1)[-1].strip()
            if value:
                names.add(value)
    return names


def test_classic_scripts_do_not_redeclare_globals():
    root = Path(__file__).resolve().parent.parent
    app_js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    prompt_js = (root / "app" / "static" / "prompt.js").read_text(encoding="utf-8")

    assert not (_global_declarations(app_js) & _global_declarations(prompt_js))
