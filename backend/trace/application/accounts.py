"""User accounts, login sessions and the system activity log.

Roles: investigator (analysis, cases, uploads) and admin (everything, plus users, settings, activity).
There is no default account or password: the first visit creates the administrator.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from trace.data_access.audit.chain import SqlAuditStore
from trace.data_access.relational.store import SqlUsers, now_iso
from trace.infrastructure.security import hash_password, new_token, token_hash, verify_password

ROLES = ("investigator", "admin")
SYSTEM = "SYSTEM"  # audit-chain subject for non-case activity
SESSION_HOURS = 12
MIN_PASSWORD = 8


class AccountError(ValueError):
    pass


def public(u: dict[str, Any]) -> dict[str, Any]:
    return {k: u[k] for k in ("id", "username", "display_name", "role", "active", "created_at", "last_login")}


def _validate(username: str, password: str | None, role: str) -> None:
    if not username or not username.strip() or len(username) > 80:
        raise AccountError("username is required")
    if role not in ROLES:
        raise AccountError(f"role must be one of {ROLES}")
    if password is not None and len(password) < MIN_PASSWORD:
        raise AccountError(f"password must be at least {MIN_PASSWORD} characters")


def setup_admin(users: SqlUsers, audit: SqlAuditStore, username: str, display_name: str, password: str) -> dict:
    if users.count() > 0:
        raise AccountError("setup is already complete")
    _validate(username, password, "admin")
    u = users.create(username.strip(), display_name.strip() or username.strip(), "admin", hash_password(password))
    audit.append(SYSTEM, u["username"], "setup_admin", {"user": u["username"]})
    return public(u)


def create_user(users: SqlUsers, audit: SqlAuditStore, actor: str, username: str, display_name: str, role: str,
                password: str) -> dict:
    _validate(username, password, role)
    if users.by_username(username.strip()):
        raise AccountError("username already exists")
    u = users.create(username.strip(), display_name.strip() or username.strip(), role, hash_password(password))
    audit.append(SYSTEM, actor, "create_user", {"user": u["username"], "role": role})
    return public(u)


def update_user(users: SqlUsers, audit: SqlAuditStore, actor: dict, uid: int, role: str | None = None,
                active: bool | None = None, password: str | None = None) -> dict:
    u = users.get(uid)
    if u is None:
        raise AccountError("user not found")
    changes: dict[str, Any] = {}
    if role is not None:
        _validate(u["username"], None, role)
        changes["role"] = role
    if active is not None:
        changes["active"] = active
    if password is not None:
        _validate(u["username"], password, u["role"])
        changes["password_hash"] = hash_password(password)
    if u["id"] == actor["id"] and (changes.get("active") is False or changes.get("role", "admin") != "admin"):
        raise AccountError("you cannot deactivate or demote your own account")
    out = users.update(uid, **changes)
    if changes.get("active") is False or "password_hash" in changes:
        users.drop_user_sessions(uid)
    audit.append(SYSTEM, actor["username"], "update_user",
                 {"user": u["username"], **{k: v for k, v in changes.items() if k != "password_hash"},
                  **({"password_reset": True} if "password_hash" in changes else {})})
    return public(out)


def login(users: SqlUsers, audit: SqlAuditStore, username: str, password: str) -> tuple[str, dict]:
    u = users.by_username(username.strip())
    if u is None or not u["active"] or not verify_password(password, u["password_hash"]):
        audit.append(SYSTEM, username.strip() or "?", "login_failed", {})
        raise AccountError("invalid username or password")
    tok, h = new_token()
    exp = (datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).isoformat(timespec="microseconds")
    users.add_session(h, u["id"], exp)
    users.update(u["id"], last_login=now_iso())
    audit.append(SYSTEM, u["username"], "login", {})
    return tok, public(u)


def logout(users: SqlUsers, tok: str) -> None:
    users.drop_session(token_hash(tok))


def user_for_token(users: SqlUsers, tok: str) -> dict | None:
    u = users.session_user(token_hash(tok))
    return public(u) if u else None
