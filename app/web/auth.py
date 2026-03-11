from __future__ import annotations

import secrets
from hmac import compare_digest

from fastapi import HTTPException, Request, status

SESSION_AUTH_KEY = "web_admin_authenticated"
SESSION_CSRF_KEY = "web_admin_csrf"
SESSION_FLASH_KEY = "web_admin_flash"


def require_web_admin_enabled(request: Request) -> None:
    settings = request.app.state.settings
    if not settings.web_admin_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Web admin is not enabled.")


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get(SESSION_AUTH_KEY))


def require_authenticated(request: Request) -> None:
    require_web_admin_enabled(request)
    if is_authenticated(request):
        return
    raise HTTPException(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Location": "/admin/login"},
        detail="Authentication required.",
    )


def login(request: Request, password: str) -> bool:
    settings = request.app.state.settings
    require_web_admin_enabled(request)
    expected = settings.web_admin_password or ""
    if not compare_digest(password, expected):
        return False
    request.session[SESSION_AUTH_KEY] = True
    ensure_csrf_token(request)
    return True


def logout(request: Request) -> None:
    request.session.clear()


def ensure_csrf_token(request: Request) -> str:
    token = request.session.get(SESSION_CSRF_KEY)
    if token:
        return token
    token = secrets.token_urlsafe(32)
    request.session[SESSION_CSRF_KEY] = token
    return token


def validate_csrf(request: Request, token: str | None) -> None:
    expected = ensure_csrf_token(request)
    if not token or not compare_digest(token, expected):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid CSRF token.")


def set_flash(request: Request, kind: str, message: str) -> None:
    request.session[SESSION_FLASH_KEY] = {"kind": kind, "message": message}


def pop_flash(request: Request) -> dict[str, str] | None:
    return request.session.pop(SESSION_FLASH_KEY, None)
