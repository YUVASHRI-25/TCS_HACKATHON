"""SQLAlchemy adapters (SQLite default, Postgres via DATABASE_URL)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (JSON, Column, DateTime, Float, Integer, MetaData, String, Table, Text, create_engine, delete,
                        insert, select)
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
              Column("data", JSON, nullable=False))

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
    return eng


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
            c.execute(delete(cases))
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
                      cases.c.n_members, cases.c.exposure_total, cases.c.finding_types)
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

    def for_case(self, case_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(select(llm_audit).where(llm_audit.c.case_id == case_id)
                                                        .order_by(llm_audit.c.id))]
