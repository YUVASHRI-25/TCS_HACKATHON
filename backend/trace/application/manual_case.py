"""Investigator-created cases.

The investigator chooses the accounts; TRACE assembles the case from the deterministic findings of the
latest run that involve them, through the same case engine (evidence, hypotheses, alternatives, score).
Such a case may not meet the automatic two-signal rule — that is shown, not hidden.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from trace.application.accounts import SYSTEM
from trace.application.build_cases import TxnIndex, build_case
from trace.domain.model.findings import Finding, node_id
from trace.domain.scoring.score import ScoringConfig
from trace.infrastructure.container import Container
from trace.intelligence.graph_analytics.networks import Network


class ManualCaseError(ValueError):
    pass


def _load_findings(c: Container) -> list[Finding]:
    p = c.settings.path(c.settings.trace_processed_dir) / "findings.json"
    if not p.exists():
        raise ManualCaseError("no analysis results yet: run the analysis first")
    out = []
    for d in json.loads(p.read_text(encoding="utf-8")):
        out.append(Finding(type=d["type"], subjects=tuple(d["subjects"]), txn_ids=tuple(d["txn_ids"]),
                           strength=d["strength"], details=d["details"], cypher_used=d["cypher_used"],
                           source=d["source"], related=tuple(d["related"]), detector=d["detector"]))
    return out


def create(c: Container, accounts: list[str], title: str, notes: str, user: str) -> dict[str, Any]:
    if not notes or not notes.strip():
        raise ManualCaseError("a note explaining why the case is opened is required")
    frames = c.frames()
    acc = frames.get("Account")
    known = set(acc["account_id"]) if acc is not None else set(frames["Transaction"]["src_account_id"])
    raw = sorted({a.split(":", 1)[1] if a.startswith("account:") else a for a in accounts})
    unknown = [a for a in raw if a not in known]
    if not raw or unknown:
        raise ManualCaseError(f"unknown or missing accounts: {unknown or 'none selected'}")
    members = {node_id("account", a) for a in raw}
    cfg = c.config
    roles = cfg.roles
    findings = _load_findings(c)
    net = Network(members=members,
                  findings=[f for f in findings if roles.get(f.type) in ("risk", "model") and members & set(f.subjects)],
                  context=[f for f in findings if roles.get(f.type) == "context" and members & set(f.subjects)])
    scfg = ScoringConfig.from_dict(cfg.detectors)
    caps = json.loads((c.settings.path(c.settings.trace_processed_dir) / "capabilities.json").read_text(encoding="utf-8"))
    derived = json.loads((c.settings.path(c.settings.trace_processed_dir) / "derived_fields.json").read_text(encoding="utf-8"))
    case = build_case(net, frames, TxnIndex(frames["Transaction"]), scfg, cfg.catalogues, caps, derived,
                      c.graph.tg.node if c.graph.tg else None).to_dict()
    n_types = len(case["score_breakdown"]["signals"])
    case["id"] = "M-" + hashlib.sha1("|".join(sorted(members)).encode()).hexdigest()[:10].upper()
    case["origin"] = "investigator"
    case["created_by"] = user
    case["title"] = title.strip() or None
    case["meets_case_rule"] = n_types >= scfg.min_types
    case["summary"] = (f"Investigator-created case{': ' + title.strip() if title.strip() else ''}. " + case["summary"]
                       + ("" if case["meets_case_rule"] else
                          f" Note: only {n_types} deterministic signal type(s); below the automatic case rule."))
    run = c.cases.latest_run()
    c.cases.add(case, run["id"] if run else 0, "investigator", user)
    c.audit.append(case["id"], user, "create_case", {"notes": notes.strip(), "accounts": raw})
    c.audit.append(SYSTEM, user, "create_case", {"case": case["id"], "accounts": len(raw)})
    return case
