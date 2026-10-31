"""Human review, adjudication and what-if use cases. Every human action is audited."""

from __future__ import annotations

from typing import Any

from trace.application.build_cases import score_inputs_from_case
from trace.data_access.audit.chain import SqlAuditStore
from trace.domain.guardrails.policy import REVIEW_ACTIONS
from trace.domain.scoring.score import ScoringConfig
from trace.domain.whatif.recompute import next_best_actions, recompute

STATUS_FOR_ACTION = {
    "confirm_for_investigation": "confirmed_for_investigation",
    "reject_false_positive": "rejected_false_positive",
    "request_more_info": "more_info_requested",
}


class ReviewError(ValueError):
    pass


def review(case: dict[str, Any], action: str, reviewer: str, notes: str, audit: SqlAuditStore) -> tuple[dict, dict]:
    if action not in REVIEW_ACTIONS:
        raise ReviewError(f"action must be one of {REVIEW_ACTIONS}")
    if not notes or not notes.strip():
        raise ReviewError("notes are required for every review action")
    if not reviewer or not reviewer.strip():
        raise ReviewError("reviewer is required")
    entry = audit.append(case["id"], reviewer.strip(), action,
                         {"notes": notes.strip(), "previous_status": case["status"],
                          "priority_score": case["priority_score"], "tier": case["tier"]})
    case = {**case, "status": STATUS_FOR_ACTION[action]}
    return case, entry


def whatif(case: dict[str, Any], adjudications: dict[str, str], facts: dict[str, Any], cfg: ScoringConfig) -> dict:
    merged = {**case.get("adjudications", {}), **adjudications}
    r = recompute(score_inputs_from_case(case), merged, facts, cfg)
    return {"simulation": True, "recorded": False, "label": "Simulation - not recorded",
            "baseline": {"score": case["priority_score"], "tier": case["tier"]},
            "score": r["score"], "tier": r["tier"], "still_opens_case": r["still_opens_case"], "changes": r["changes"],
            "breakdown": r["breakdown"]}


def adjudicate(case: dict[str, Any], fact: str, state: str, reviewer: str, note: str, facts: dict[str, Any],
               cfg: ScoringConfig, audit: SqlAuditStore) -> tuple[dict, dict]:
    if fact not in facts:
        raise ReviewError(f"unknown fact {fact!r}")
    if state not in ("confirmed", "refuted", "unknown"):
        raise ReviewError("state must be confirmed, refuted or unknown")
    if not note or not note.strip() or not reviewer or not reviewer.strip():
        raise ReviewError("reviewer and note are required to record a finding")
    adj = {**case.get("adjudications", {}), fact: state}
    r = recompute(score_inputs_from_case(case), adj, facts, cfg)
    entry = audit.append(case["id"], reviewer.strip(), "adjudicate",
                         {"fact": fact, "state": state, "note": note.strip(), "score_after": r["score"], "tier_after": r["tier"]})
    case = {**case, "adjudications": adj,
            "adjudicated": {"score": r["score"], "tier": r["tier"], "changes": r["changes"],
                            "note": "Score after investigator-recorded facts; the original priority score is unchanged."}}
    return case, entry


def nba(case: dict[str, Any], facts: dict[str, Any], cfg: ScoringConfig) -> list[dict[str, Any]]:
    return next_best_actions(score_inputs_from_case(case), case.get("adjudications", {}), facts, cfg)


def reapply_reviews(case_dicts: list[dict[str, Any]], audit: SqlAuditStore) -> list[dict[str, Any]]:
    """After a pipeline re-run, restore status and recorded facts from the audit log."""
    out = []
    for c in case_dicts:
        status, adj = c["status"], {}
        for e in audit.chain(c["id"]):
            if e["action"] in STATUS_FOR_ACTION:
                status = STATUS_FOR_ACTION[e["action"]]
            elif e["action"] == "adjudicate":
                adj[e["payload"]["fact"]] = e["payload"]["state"]
        out.append({**c, "status": status, "adjudications": adj})
    return out
