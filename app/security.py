import base64
import secrets

from starlette.datastructures import Headers
from starlette.responses import Response

from .config import get_settings


_UNAUTHORIZED_HEADERS = {
    "WWW-Authenticate": 'Basic realm="ReelReverse", charset="UTF-8"',
    "Cache-Control": "no-store",
}


def decode_basic_auth(header: str) -> tuple[str, str] | None:
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "basic" or not token:
        return None
    try:
        decoded = base64.b64decode(token, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    username, separator, password = decoded.partition(":")
    if not separator:
        return None
    return username, password


def verify_basic_auth(header: str, username: str, password: str) -> bool:
    credentials = decode_basic_auth(header)
    if credentials is None:
        return False
    supplied_username, supplied_password = credentials
    user_ok = secrets.compare_digest(
        supplied_username.encode("utf-8"), username.encode("utf-8")
    )
    password_ok = secrets.compare_digest(
        supplied_password.encode("utf-8"), password.encode("utf-8")
    )
    return user_ok and password_ok


class BasicAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        if not settings.app_password or scope["path"] == "/healthz":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if verify_basic_auth(
            headers.get("authorization", ""),
            settings.app_username,
            settings.app_password,
        ):
            await self.app(scope, receive, send)
            return

        response = Response(
            "Unauthorized",
            status_code=401,
            headers=_UNAUTHORIZED_HEADERS,
        )
        await response(scope, receive, send)
