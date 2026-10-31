"""Append-only, hash-chained audit log. entry.hash = sha256(prev_hash + canonical_json(entry))."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.engine import Engine

from trace.data_access.ports import AuditStore
from trace.data_access.relational.store import audit_log, now_iso

GENESIS = "0" * 64


def entry_hash(prev_hash: str, case_id: str, ts: str, actor: str, action: str, payload: str) -> str:
    body = json.dumps({"case_id": case_id, "ts": ts, "actor": actor, "action": action, "payload": payload},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + body).encode("utf-8")).hexdigest()


class SqlAuditStore(AuditStore):
    """One global chain across all cases (tampering with any entry breaks every later hash)."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def append(self, case_id: str, actor: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.engine.begin() as c:
            last = c.execute(select(audit_log.c.hash).order_by(audit_log.c.seq.desc()).limit(1)).first()
            prev = last[0] if last else GENESIS
            ts = now_iso()
            p = json.dumps(payload, sort_keys=True, default=str)
            h = entry_hash(prev, case_id, ts, actor, action, p)
            seq = c.execute(insert(audit_log).values(case_id=case_id, ts=ts, actor=actor, action=action, payload=p,
                                                     prev_hash=prev, hash=h)).inserted_primary_key[0]
        return {"seq": seq, "case_id": case_id, "ts": ts, "actor": actor, "action": action, "payload": payload,
                "prev_hash": prev, "hash": h}

    def _all(self) -> list[Any]:
        with self.engine.connect() as c:
            return list(c.execute(select(audit_log).order_by(audit_log.c.seq)))

    def chain(self, case_id: str) -> list[dict[str, Any]]:
        return [{"seq": r.seq, "case_id": r.case_id, "ts": r.ts, "actor": r.actor, "action": r.action,
                 "payload": json.loads(r.payload), "prev_hash": r.prev_hash, "hash": r.hash}
                for r in self._all() if r.case_id == case_id]

    def verify(self, case_id: str | None = None) -> bool:
        return self.verify_detail()["valid"]

    def verify_detail(self) -> dict[str, Any]:
        prev = GENESIS
        rows = self._all()
        for r in rows:
            if r.prev_hash != prev or entry_hash(prev, r.case_id, r.ts, r.actor, r.action, r.payload) != r.hash:
                return {"valid": False, "entries": len(rows), "broken_at_seq": r.seq}
            prev = r.hash
        return {"valid": True, "entries": len(rows), "broken_at_seq": None}
