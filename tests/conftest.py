"""Shared pytest defaults for local, authentication-free test clients."""

import pytest

from app.api.share_routes import reset_comment_limits_for_tests
from app.security import reset_auth_failures_for_tests


@pytest.fixture(autouse=True)
def explicit_insecure_test_mode(monkeypatch):
    """Opt tests into the same explicit local-development switch as ``.env``.

    Production remains fail-closed; individual security tests clear this variable
    to verify that a missing password is rejected.
    """
    monkeypatch.setenv("ALLOW_INSECURE_NO_AUTH", "true")
    reset_auth_failures_for_tests()
    reset_comment_limits_for_tests()
    yield
    reset_auth_failures_for_tests()
    reset_comment_limits_for_tests()
