"""Authentication dependencies: bearer session tokens, role checks."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from trace.application.accounts import user_for_token
from trace.infrastructure.container import Container, get_container


def bearer(request: Request) -> str | None:
    h = request.headers.get("Authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return request.query_params.get("token")  # for file downloads opened in a new tab


def current_user(request: Request, c: Container = Depends(get_container)) -> dict:
    tok = bearer(request)
    u = user_for_token(c.users, tok) if tok else None
    if u is None:
        raise HTTPException(401, "not signed in or session expired")
    return u


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "administrator role required")
    return user
