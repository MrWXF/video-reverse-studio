import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
