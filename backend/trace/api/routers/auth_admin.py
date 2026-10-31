"""Sign-in, first-run setup, datasets/uploads, and administrator endpoints."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from trace.api.deps import bearer, current_user, require_admin
from trace.application import accounts, datasets, settings_admin
from trace.application.accounts import SYSTEM, AccountError
from trace.infrastructure.container import Container, get_container

router = APIRouter(prefix="/api", tags=["access"])


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: Literal["investigator", "admin"]
    active: bool
    created_at: str
    last_login: str | None


class SetupState(BaseModel):
    needs_setup: bool


class SetupIn(BaseModel):
    username: str = Field(min_length=1)
    display_name: str = ""
    password: str = Field(min_length=8)


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    token: str
    user: UserOut


class UserCreateIn(BaseModel):
    username: str = Field(min_length=1)
    display_name: str = ""
    role: Literal["investigator", "admin"]
    password: str = Field(min_length=8)


class UserUpdateIn(BaseModel):
    role: Literal["investigator", "admin"] | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class DatasetFile(BaseModel):
    table: str
    file: str | None
    rows: int | None


class DatasetOut(BaseModel):
    id: int
    name: str
    created_at: str
    created_by: str
    status: Literal["ready", "rejected", "active"]
    files: list[DatasetFile]
    message: str | None


class RunOut(BaseModel):
    id: int
    dataset_id: int
    triggered_by: str
    started_at: str
    finished_at: str | None
    status: Literal["running", "succeeded", "failed"]
    summary: dict[str, Any] | None
    error: str | None


class ActivityEntry(BaseModel):
    seq: int
    case_id: str
    ts: str
    actor: str
    action: str
    payload: dict[str, Any]
    hash: str


class ActivityOut(BaseModel):
    entries: list[ActivityEntry]
    chain_valid: bool
    chain_entries: int
    broken_at_seq: int | None


class DeriveSetting(BaseModel):
    metric: str | None = None
    percentile: float


class DetectorSettings(BaseModel):
    params: dict[str, float] = {}
    derive: dict[str, DeriveSetting] = {}


class SettingsView(BaseModel):
    case_rules: dict[str, float] = {}
    tiers: dict[str, float] = {}
    weights: dict[str, float] = {}
    ml_weights: dict[str, float] = {}
    penalties: dict[str, float] = {}
    detectors: dict[str, DetectorSettings] = {}


class SettingsSaved(BaseModel):
    changes: list[dict[str, Any]]
    note: str


def _err(e: Exception) -> HTTPException:
    return HTTPException(422, str(e))


# --------------------------------------------------------------------------------- sign-in
@router.get("/auth/setup", response_model=SetupState)
def setup_state(c: Container = Depends(get_container)):
    return {"needs_setup": c.users.count() == 0}


@router.post("/auth/setup", response_model=UserOut)
def setup(body: SetupIn, c: Container = Depends(get_container)):
    try:
        return accounts.setup_admin(c.users, c.audit, body.username, body.display_name, body.password)
    except AccountError as e:
        raise _err(e) from e


@router.post("/auth/login", response_model=LoginOut)
def login(body: LoginIn, c: Container = Depends(get_container)):
    try:
        tok, user = accounts.login(c.users, c.audit, body.username, body.password)
    except AccountError as e:
        raise HTTPException(401, str(e)) from e
    return {"token": tok, "user": user}


@router.post("/auth/logout")
def logout(request: Request, c: Container = Depends(get_container)) -> dict:
    tok = bearer(request)
    if tok:
        accounts.logout(c.users, tok)
    return {"ok": True}


@router.get("/auth/me", response_model=UserOut)
def me(user: dict = Depends(current_user)):
    return user


# --------------------------------------------------------------------------------- datasets
@router.get("/datasets", response_model=list[DatasetOut])
def list_datasets(_: dict = Depends(current_user), c: Container = Depends(get_container)):
    datasets.ensure_configured_dataset(c)
    return c.datasets.list()


@router.post("/datasets/upload", response_model=DatasetOut)
async def upload_dataset(name: str = Form(""), files: list[UploadFile] = File(...),
                         user: dict = Depends(current_user), c: Container = Depends(get_container)):
    datasets.ensure_configured_dataset(c)
    data = [(f.filename or "upload.csv", await f.read()) for f in files]
    try:
        out = datasets.upload(c, name, data, user["username"])
    except datasets.DatasetError as e:
        raise _err(e) from e
    if out["status"] == "rejected":  # the rejection stays in the history, but the caller must not see success
        raise HTTPException(422, out.get("message") or "upload rejected")
    return out


@router.post("/datasets/{dataset_id}/run", response_model=RunOut)
def run_dataset(dataset_id: int, user: dict = Depends(current_user), c: Container = Depends(get_container)):
    try:
        rid = datasets.start_run(c, dataset_id, user["username"])
    except datasets.DatasetError as e:
        raise HTTPException(409, str(e)) from e
    return next(r for r in c.datasets.runs() if r["id"] == rid)


@router.get("/datasets/runs", response_model=list[RunOut])
def list_runs(_: dict = Depends(current_user), c: Container = Depends(get_container)):
    return c.datasets.runs()


# --------------------------------------------------------------------------------- admin
@router.get("/admin/users", response_model=list[UserOut])
def list_users(_: dict = Depends(require_admin), c: Container = Depends(get_container)):
    return [accounts.public(u) for u in c.users.list()]


@router.post("/admin/users", response_model=UserOut)
def create_user(body: UserCreateIn, admin: dict = Depends(require_admin), c: Container = Depends(get_container)):
    try:
        return accounts.create_user(c.users, c.audit, admin["username"], body.username, body.display_name, body.role,
                                    body.password)
    except AccountError as e:
        raise _err(e) from e


@router.patch("/admin/users/{uid}", response_model=UserOut)
def update_user(uid: int, body: UserUpdateIn, admin: dict = Depends(require_admin),
                c: Container = Depends(get_container)):
    try:
        return accounts.update_user(c.users, c.audit, admin, uid, body.role, body.active, body.password)
    except AccountError as e:
        raise _err(e) from e


@router.get("/admin/settings", response_model=SettingsView)
def get_settings_view(_: dict = Depends(require_admin), c: Container = Depends(get_container)):
    return settings_admin.editable(c.settings)


@router.put("/admin/settings", response_model=SettingsSaved)
def put_settings(patch: SettingsView, admin: dict = Depends(require_admin), c: Container = Depends(get_container)):
    try:
        return settings_admin.apply(c.settings, c.audit, admin["username"], patch.model_dump(exclude_none=True))
    except settings_admin.SettingsError as e:
        raise _err(e) from e


@router.get("/admin/activity", response_model=ActivityOut)
def activity(limit: int = 300, _: dict = Depends(require_admin), c: Container = Depends(get_container)):
    v = c.audit.verify_detail()
    rows = c.audit.all_entries()[-limit:][::-1]
    return {"entries": rows, "chain_valid": v["valid"], "chain_entries": v["entries"], "broken_at_seq": v["broken_at_seq"]}


__all__ = ["router", "SYSTEM"]


@router.get("/admin/system-health")
def system_health(_: dict = Depends(require_admin), c: Container = Depends(get_container)) -> dict[str, Any]:
    """Live checks: database round-trip, graph state, LLM connectivity (real provider call) and failure counters."""
    import time

    from sqlalchemy import text

    from trace.intelligence.llm.client import STATS

    out: dict[str, Any] = {"backend": {"status": "ok"}}
    try:
        t0 = time.time()
        with c.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        out["database"] = {"connected": True, "dialect": c.engine.dialect.name,
                           "latency_ms": int((time.time() - t0) * 1000), "cases": len(c.cases.all_rows()),
                           "users": c.users.count()}
    except Exception as e:  # noqa: BLE001 - reported to the administrator verbatim
        out["database"] = {"connected": False, "error": f"{type(e).__name__}: {e}"}
    run = c.cases.latest_run()
    try:
        tg = c.graph.tg
        out["graph"] = {"status": "ready" if tg is not None else "no graph (no pipeline run)",
                        "backend": c.settings.graph_backend, "nodes": tg.g.number_of_nodes() if tg else 0,
                        "edges": tg.g.number_of_edges() if tg else 0,
                        "last_pipeline_run": run["id"] if run else None}
    except Exception as e:  # noqa: BLE001
        out["graph"] = {"status": "failed", "error": f"{type(e).__name__}: {e}"}
    ping = c.llm.ping()
    llm_rows = c.llm_audit.all_recent(200) if hasattr(c.llm_audit, "all_recent") else []
    out["llm"] = {**ping, "configured": c.llm.configured, "model": c.llm.model, "base_url": c.llm.base_url,
                  "api_key_set": bool(c.llm.api_key), "requests_since_start": STATS.requests,
                  "failures_since_start": STATS.failures, "last_error": STATS.last_error,
                  "last_latency_ms": STATS.last_latency_ms, "recent_errors": STATS.recent_errors,
                  "persisted_calls": len(llm_rows), "persisted_failures": sum(1 for r in llm_rows if r["status"] != "ok")}
    return out


@router.get("/admin/cases")
def all_cases(_: dict = Depends(require_admin), c: Container = Depends(get_container)) -> list[dict[str, Any]]:
    return c.cases.list(limit=5000)
