import base64

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.security import decode_basic_auth, verify_basic_auth


@pytest.fixture(autouse=True)
def reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def basic_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


def test_decode_basic_auth():
    assert decode_basic_auth(basic_header("admin", "secret")) == ("admin", "secret")
    assert decode_basic_auth("Bearer abc") is None
    assert decode_basic_auth("Basic !!!") is None
    assert decode_basic_auth(basic_header("missing-password", "")) == (
        "missing-password",
        "",
    )


def test_verify_basic_auth():
    header = basic_header("admin", "secret")
    assert verify_basic_auth(header, "admin", "secret")
    assert not verify_basic_auth(header, "admin", "wrong")
    assert not verify_basic_auth(header, "other", "secret")
    assert not verify_basic_auth("", "admin", "secret")


def test_auth_disabled_allows_requests(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    get_settings.cache_clear()
    client = TestClient(app)

    assert client.get("/").status_code == 200
    assert client.get("/files/app.db").status_code == 404


def test_auth_enabled_protects_app_and_business_api(monkeypatch):
    monkeypatch.setenv("APP_USERNAME", "alice")
    monkeypatch.setenv("APP_PASSWORD", "secret")
    get_settings.cache_clear()
    client = TestClient(app)

    unauthorized = client.get("/")
    assert unauthorized.status_code == 401
    assert unauthorized.headers["www-authenticate"].startswith("Basic")

    assert client.get("/", auth=("alice", "wrong")).status_code == 401
    assert client.get("/", auth=("alice", "secret")).status_code == 200
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/projects").status_code == 401
