"""SQLAlchemy adapters (SQLite default, Postgres via DATABASE_URL)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, Integer, MetaData, String, Table, Text, create_engine,
                        delete, insert, inspect, select, text, update)
from sqlalchemy.engine import Engine

from trace.data_access.ports import CaseRepository

metadata = MetaData()

runs = Table("pipeline_runs", metadata,
             Column("id", Integer, primary_key=True, autoincrement=True),
             Column("created_at", DateTime(timezone=True), nullable=False),
             Column("summary", JSON, nullable=False))

cases = Table("cases", metadata,
              Column("id", String(32), primary_key=True),
              Column("run_id", Integer, nullable=False),
              Column("tier", String(8), nullable=False, index=True),
              Column("priority_score", Float, nullable=False, index=True),
              Column("status", String(32), nullable=False, index=True),
              Column("summary", Text, nullable=False),
              Column("n_members", Integer, nullable=False),
              Column("exposure_total", Float, nullable=False),
              Column("finding_types", JSON, nullable=False),
              Column("origin", String(16), nullable=False, server_default="pipeline"),
              Column("created_by", String(120)),
              Column("data", JSON, nullable=False))

users = Table("users", metadata,
              Column("id", Integer, primary_key=True, autoincrement=True),
              Column("username", String(80), unique=True, nullable=False),
              Column("display_name", String(120), nullable=False),
              Column("role", String(16), nullable=False),            # investigator | admin
              Column("password_hash", String(200), nullable=False),
              Column("active", Boolean, nullable=False, default=True),
              Column("created_at", String(40), nullable=False),
              Column("last_login", String(40)))

sessions = Table("sessions", metadata,
                 Column("token_hash", String(64), primary_key=True),
                 Column("user_id", Integer, nullable=False, index=True),
                 Column("created_at", String(40), nullable=False),
                 Column("expires_at", String(40), nullable=False))

datasets = Table("datasets", metadata,
                 Column("id", Integer, primary_key=True, autoincrement=True),
                 Column("name", String(200), nullable=False),
                 Column("created_at", String(40), nullable=False),
                 Column("created_by", String(120), nullable=False),
                 Column("status", String(16), nullable=False),          # ready | rejected | active
                 Column("mapping_path", Text),
                 Column("files", JSON, nullable=False),
                 Column("message", Text))

dataset_runs = Table("dataset_runs", metadata,
                     Column("id", Integer, primary_key=True, autoincrement=True),
                     Column("dataset_id", Integer, nullable=False, index=True),
                     Column("triggered_by", String(120), nullable=False),
                     Column("started_at", String(40), nullable=False),
                     Column("finished_at", String(40)),
                     Column("status", String(16), nullable=False),      # running | succeeded | failed
                     Column("summary", JSON),
                     Column("error", Text))

audit_log = Table("audit_log", metadata,
                  Column("seq", Integer, primary_key=True, autoincrement=True),
                  Column("case_id", String(32), index=True, nullable=False),
                  Column("ts", String(40), nullable=False),
                  Column("actor", String(120), nullable=False),
                  Column("action", String(64), nullable=False),
                  Column("payload", Text, nullable=False),
                  Column("prev_hash", String(64), nullable=False),
                  Column("hash", String(64), nullable=False))

llm_audit = Table("llm_audit", metadata,
                  Column("id", Integer, primary_key=True, autoincrement=True),
                  Column("case_id", String(32), index=True, nullable=False),
                  Column("ts", String(40), nullable=False),
                  Column("agent", String(64), nullable=False),
                  Column("provider", String(32), nullable=False),
                  Column("prompt", Text, nullable=False),
                  Column("response", Text),
                  Column("status", String(32), nullable=False))


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite:///"):
        from pathlib import Path
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    eng = create_engine(url, future=True)
    metadata.create_all(eng)
    _migrate(eng)
    return eng


def _migrate(eng: Engine) -> None:
    """Additive columns for databases created by earlier versions."""
    have = {c["name"] for c in inspect(eng).get_columns("cases")}
    with eng.begin() as c:
        if "origin" not in have:
            c.execute(text("ALTER TABLE cases ADD COLUMN origin VARCHAR(16) NOT NULL DEFAULT 'pipeline'"))
        if "created_by" not in have:
            c.execute(text("ALTER TABLE cases ADD COLUMN created_by VARCHAR(120)"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class SqlCaseRepository(CaseRepository):
    def __init__(self, engine: Engine):
        self.engine = engine

    def replace_all(self, run_summary: dict[str, Any], case_dicts: list[dict[str, Any]]) -> int:
        """Idempotent pipeline write: one new run row; the case table is rewritten. Audit is untouched."""
        with self.engine.begin() as c:
            run_id = c.execute(insert(runs).values(created_at=datetime.now(timezone.utc),
                                                   summary=json.loads(json.dumps(run_summary, default=str)))).inserted_primary_key[0]
            # Investigator-created cases are kept across pipeline runs.
            c.execute(delete(cases).where(cases.c.origin == "pipeline"))
            if case_dicts:
                c.execute(insert(cases), [self._row(run_id, d) for d in case_dicts])
        return run_id

    @staticmethod
    def _row(run_id: int, d: dict[str, Any]) -> dict[str, Any]:
        d = json.loads(json.dumps(d, default=str))
        return {"id": d["id"], "run_id": run_id, "tier": d["tier"], "priority_score": d["priority_score"],
                "status": d["status"], "summary": d["summary"],
                "n_members": sum(1 for e in d["entities"] if e["role"] == "member"),
                "exposure_total": d["exposure"].get("total", 0.0), "finding_types": d["finding_types"], "data": d}

    def add(self, case: dict[str, Any], run_id: int, origin: str, created_by: str) -> None:
        row = self._row(run_id, case) | {"origin": origin, "created_by": created_by}
        with self.engine.begin() as c:
            c.execute(delete(cases).where(cases.c.id == case["id"]))
            c.execute(insert(cases).values(**row))

    def save(self, case: dict[str, Any]) -> None:
        with self.engine.begin() as c:
            c.execute(cases.update().where(cases.c.id == case["id"]).values(
                status=case["status"], data=json.loads(json.dumps(case, default=str))))

    def get(self, case_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as c:
            r = c.execute(select(cases.c.data).where(cases.c.id == case_id)).first()
        return r[0] if r else None

    def list(self, tier: str | None = None, status: str | None = None, q: str | None = None,
             limit: int = 500, offset: int = 0) -> list[dict[str, Any]]:
        stmt = select(cases.c.id, cases.c.tier, cases.c.priority_score, cases.c.status, cases.c.summary,
                      cases.c.n_members, cases.c.exposure_total, cases.c.finding_types, cases.c.origin,
                      cases.c.created_by)
        if tier:
            stmt = stmt.where(cases.c.tier == tier.upper())
        if status:
            stmt = stmt.where(cases.c.status == status)
        if q:
            stmt = stmt.where(cases.c.summary.ilike(f"%{q}%") | cases.c.id.ilike(f"%{q}%"))
        stmt = stmt.order_by(cases.c.priority_score.desc()).limit(limit).offset(offset)
        with self.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(stmt)]

    def all_rows(self) -> list[dict[str, Any]]:
        return self.list(limit=10**9)

    def latest_run(self) -> dict[str, Any] | None:
        with self.engine.connect() as c:
            r = c.execute(select(runs).order_by(runs.c.id.desc()).limit(1)).first()
        return {"id": r.id, "created_at": str(r.created_at), **r.summary} if r else None


class SqlLlmAudit:
    def __init__(self, engine: Engine):
        self.engine = engine

    def record(self, case_id: str, agent: str, provider: str, prompt: str, response: str | None, status: str) -> None:
        with self.engine.begin() as c:
            c.execute(insert(llm_audit).values(case_id=case_id, ts=now_iso(), agent=agent, provider=provider,
                                               prompt=prompt, response=response, status=status))

    def all_recent(self, n: int = 200) -> list[dict[str, Any]]:
        with self.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(select(llm_audit).order_by(llm_audit.c.id.desc()).limit(n))]

    def for_case(self, case_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(select(llm_audit).where(llm_audit.c.case_id == case_id)
                                                        .order_by(llm_audit.c.id))]


class SqlUsers:
    def __init__(self, engine: Engine):
        self.engine = engine

    def count(self) -> int:
        with self.engine.connect() as c:
            return len(c.execute(select(users.c.id)).all())

    def create(self, username: str, display_name: str, role: str, password_hash: str) -> dict[str, Any]:
        with self.engine.begin() as c:
            uid = c.execute(insert(users).values(username=username, display_name=display_name, role=role,
                                                 password_hash=password_hash, active=True,
                                                 created_at=now_iso())).inserted_primary_key[0]
        return self.get(uid)

    def get(self, uid: int) -> dict[str, Any] | None:
        with self.engine.connect() as c:
            r = c.execute(select(users).where(users.c.id == uid)).first()
        return dict(r._mapping) if r else None

    def by_username(self, username: str) -> dict[str, Any] | None:
        with self.engine.connect() as c:
            r = c.execute(select(users).where(users.c.username == username)).first()
        return dict(r._mapping) if r else None

    def list(self) -> list[dict[str, Any]]:
        with self.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(select(users).order_by(users.c.id))]

    def update(self, uid: int, **values: Any) -> dict[str, Any] | None:
        with self.engine.begin() as c:
            c.execute(update(users).where(users.c.id == uid).values(**values))
        return self.get(uid)

    def add_session(self, token_hash: str, uid: int, expires_at: str) -> None:
        with self.engine.begin() as c:
            c.execute(insert(sessions).values(token_hash=token_hash, user_id=uid, created_at=now_iso(),
                                              expires_at=expires_at))

    def session_user(self, token_hash: str) -> dict[str, Any] | None:
        with self.engine.connect() as c:
            r = c.execute(select(sessions).where(sessions.c.token_hash == token_hash)).first()
        if r is None or r.expires_at < now_iso():
            return None
        u = self.get(r.user_id)
        return u if u and u["active"] else None

    def drop_session(self, token_hash: str) -> None:
        with self.engine.begin() as c:
            c.execute(delete(sessions).where(sessions.c.token_hash == token_hash))

    def drop_user_sessions(self, uid: int) -> None:
        with self.engine.begin() as c:
            c.execute(delete(sessions).where(sessions.c.user_id == uid))


class SqlDatasets:
    def __init__(self, engine: Engine):
        self.engine = engine

    def create(self, name: str, created_by: str, status: str, files: list[dict], mapping_path: str | None,
               message: str | None) -> dict[str, Any]:
        with self.engine.begin() as c:
            did = c.execute(insert(datasets).values(name=name, created_at=now_iso(), created_by=created_by,
                                                    status=status, files=files, mapping_path=mapping_path,
                                                    message=message)).inserted_primary_key[0]
        return self.get(did)

    def get(self, did: int) -> dict[str, Any] | None:
        with self.engine.connect() as c:
            r = c.execute(select(datasets).where(datasets.c.id == did)).first()
        return dict(r._mapping) if r else None

    def list(self) -> list[dict[str, Any]]:
        with self.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(select(datasets).order_by(datasets.c.id.desc()))]

    def set_active(self, did: int) -> None:
        with self.engine.begin() as c:
            c.execute(update(datasets).where(datasets.c.status == "active").values(status="ready"))
            c.execute(update(datasets).where(datasets.c.id == did).values(status="active"))

    def start_run(self, did: int, user: str) -> int:
        with self.engine.begin() as c:
            return c.execute(insert(dataset_runs).values(dataset_id=did, triggered_by=user, started_at=now_iso(),
                                                         status="running")).inserted_primary_key[0]

    def finish_run(self, rid: int, status: str, summary: dict | None = None, error: str | None = None) -> None:
        import json
        with self.engine.begin() as c:
            c.execute(update(dataset_runs).where(dataset_runs.c.id == rid).values(
                finished_at=now_iso(), status=status, error=error,
                summary=json.loads(json.dumps(summary, default=str)) if summary else None))

    def runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(select(dataset_runs).order_by(dataset_runs.c.id.desc()).limit(limit))]

    def running(self) -> bool:
        with self.engine.connect() as c:
            return c.execute(select(dataset_runs.c.id).where(dataset_runs.c.status == "running")).first() is not None

    def fail_stale_runs(self) -> None:
        """A run still marked running at startup was interrupted by a restart."""
        with self.engine.begin() as c:
            c.execute(update(dataset_runs).where(dataset_runs.c.status == "running").values(
                status="failed", finished_at=now_iso(), error="interrupted (server restarted during the run)"))
