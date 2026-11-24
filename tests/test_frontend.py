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
